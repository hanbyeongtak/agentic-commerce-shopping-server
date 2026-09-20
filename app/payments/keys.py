"""GoBTC Pay 연동에 필요한 키/서명 로직 (Part 1 판매자 지갑, Part 2 구매자 키, Part 3 PSBT 서명)."""
import hashlib
import os
from dataclasses import dataclass

from embit import bip32, bip39, ec
from embit.networks import NETWORKS
from embit.psbt import PSBT
from embit.util import secp256k1

from app.payments.errors import PaymentError

MERCHANT_DERIVATION_PATH = "m/84'/0'/0'"
MAINNET = NETWORKS["main"]


@dataclass
class MerchantWallet:
    mnemonic: str
    xpub: str
    master_fingerprint: str
    derivation_path: str = MERCHANT_DERIVATION_PATH


def wallet_from_mnemonic(mnemonic: str) -> MerchantWallet:
    root = bip32.HDKey.from_seed(bip39.mnemonic_to_seed(mnemonic))
    xpub = root.derive(MERCHANT_DERIVATION_PATH).to_public().to_base58()
    if not xpub.startswith("xpub"):  # 서버가 ypub/zpub 는 거부한다
        raise PaymentError("Derived key is not an xpub")
    return MerchantWallet(mnemonic=mnemonic, xpub=xpub, master_fingerprint=root.my_fingerprint.hex())


def generate_merchant_wallet() -> MerchantWallet:
    return wallet_from_mnemonic(bip39.mnemonic_from_bytes(os.urandom(16)))  # 12 words


def generate_payer_key() -> tuple[str, str]:
    """(개인키 hex, 압축 공개키 hex)"""
    priv = ec.PrivateKey(os.urandom(32))
    return priv.secret.hex(), priv.get_public_key().sec().hex()


def _varint(n: int) -> bytes:
    if n < 0xFD:
        return bytes([n])
    if n <= 0xFFFF:
        return bytes([0xFD, n & 0xFF, n >> 8])
    raise ValueError("message too long")


def bitcoin_message_hash(message: str) -> bytes:
    msg = message.encode()
    data = b"\x18Bitcoin Signed Message:\n" + _varint(len(msg)) + msg
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def sign_challenge(priv_hex: str, message: str) -> str:
    """Bitcoin Signed Message 방식으로 서명한 64바이트 r‖s (128 hex). 이미 해시된 값에 바로 서명한다."""
    sig = ec.PrivateKey(bytes.fromhex(priv_hex)).sign(bitcoin_message_hash(message))
    return secp256k1.ecdsa_signature_serialize_compact(sig._sig).hex()


def verify_payment_psbt(psbt_b64: str, pay_address: str, pay_sats: int, change_address: str, max_fee_sats: int) -> int:
    """서명 전에 서버가 준 PSBT 가 정확히 의도한 결제인지 확인한다.

    - pay_address 로 pay_sats 를 보내는 출력이 정확히 1개
    - 나머지 출력은 전부 구매자 본인 지갑(잔돈)
    - 수수료가 상한 이하
    검증을 통과하면 수수료(sats)를 반환한다.
    """
    psbt = PSBT.from_base64(psbt_b64)
    pay_outputs, others = [], []
    for out in psbt.tx.vout:
        address = out.script_pubkey.address(MAINNET)
        (pay_outputs if address.lower() == pay_address.lower() else others).append((address, out.value))

    if len(pay_outputs) != 1 or pay_outputs[0][1] != pay_sats:
        raise PaymentError(f"PSBT payment output mismatch (expected {pay_sats} sats to {pay_address})")
    for address, _ in others:
        if address.lower() != change_address.lower():
            raise PaymentError(f"PSBT has unexpected output to {address}")

    fee = sum(inp.utxo.value for inp in psbt.inputs) - sum(out.value for out in psbt.tx.vout)
    if fee < 0 or fee > max_fee_sats:
        raise PaymentError(f"PSBT fee {fee} sats is out of range (max {max_fee_sats})")
    return fee


def sign_psbt(psbt_b64: str, priv_hex: str) -> str:
    """모든 입력에 서명한다. finalize 하지 않는다(플랫폼이 두 번째 서명을 추가)."""
    psbt = PSBT.from_base64(psbt_b64)
    signed = psbt.sign_with(ec.PrivateKey(bytes.fromhex(priv_hex)))
    if signed != len(psbt.inputs):
        raise PaymentError(f"Signed {signed} of {len(psbt.inputs)} PSBT inputs")
    return psbt.to_base64()
