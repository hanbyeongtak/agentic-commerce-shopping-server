"""결제 시스템 서비스: 판매자 온보딩, 구매자 지갑 준비, 주문 결제."""
import logging
import time
from decimal import ROUND_UP, Decimal, InvalidOperation

from app.config import settings
from app.db import get_conn
from app.payments import client, keys, ledger
from app.payments.crypto import decrypt, encrypt
from app.payments.errors import PaymentError

log = logging.getLogger("payments")

SATS_PER_BTC = 100_000_000
DUST_SATS = 546  # 이보다 작은 결제는 서버가 거부한다
MAX_FEE_SATS = 10_000  # PSBT 수수료 안전 상한
JWT_TTL_SECONDS = 8 * 60  # 서버 토큰 유효시간 10분보다 짧게 캐시

_jwt_cache: dict[str, tuple[str, float]] = {}


# ---------------------------------------------------------------- 판매자

def onboard_merchant(email: str, code: str) -> dict:
    """이메일 인증 → xpub 연결 → API 키 발급 후 저장한다. 인증 코드는 한 번만 쓸 수 있고 토큰은 10분 유효하다."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT user_id, merchant_xpub, merchant_mnemonic_enc, secret FROM users WHERE email = %s", (email,)
        )
        user = cur.fetchone()
        if user is None:
            raise LookupError("user not found")
        if not user["user_id"]:
            raise PaymentError("머천트 등록이 아직 안 된 회원입니다 (merchant_register_batch 먼저 실행)")
        if user["secret"]:
            raise PaymentError("이미 머천트 설정이 완료된 회원입니다")

        # 지갑은 API 호출 전에 먼저 저장한다. 니모닉을 잃으면 받은 BTC 를 쓸 수 없다.
        if user["merchant_mnemonic_enc"]:
            wallet = keys.wallet_from_mnemonic(decrypt(user["merchant_mnemonic_enc"]))
        else:
            wallet = keys.generate_merchant_wallet()
            cur.execute(
                "UPDATE users SET merchant_mnemonic_enc = %s, merchant_xpub = %s WHERE email = %s",
                (encrypt(wallet.mnemonic), wallet.xpub, email),
            )

        verified = client.verify_email(email, code)
        token = verified["accessToken"]
        memberships = verified.get("memberships") or []
        merchant_id = memberships[0].get("merchantId") if memberships else None
        if merchant_id:
            cur.execute("UPDATE users SET merchant_id = %s WHERE email = %s", (merchant_id, email))

        client.link_xpub(token, wallet.xpub, wallet.derivation_path, wallet.master_fingerprint, "Agent merchant wallet")
        api_key = client.create_api_key(token, "Agent key")
        cur.execute(
            "UPDATE users SET prefix = %s, secret = %s, type = %s WHERE email = %s",
            (api_key.get("prefix"), encrypt(api_key["secret"]), api_key.get("type"), email),
        )
    return {"email": email, "merchant_id": merchant_id, "xpub": wallet.xpub}


# ---------------------------------------------------------------- 구매자

def setup_buyer_wallet(email: str) -> str | None:
    """구매자 키 생성 → 즉시 저장 → 지갑 등록 → 입금 주소 저장. 이미 끝났으면 None."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT wallet_pubkey, wallet_address, wallet_private_key_enc FROM users WHERE email = %s", (email,)
        )
        user = cur.fetchone()
        if user is None or user["wallet_address"]:
            return None

        pubkey = user["wallet_pubkey"]
        if not user["wallet_private_key_enc"]:
            # 개인키는 지갑 등록 호출 전에 저장한다. 등록 후 죽어도 키를 잃지 않게 한다.
            priv_hex, pubkey = keys.generate_payer_key()
            cur.execute(
                "UPDATE users SET wallet_private_key_enc = %s, wallet_pubkey = %s "
                "WHERE email = %s AND wallet_private_key_enc IS NULL",
                (encrypt(priv_hex), pubkey, email),
            )
            if cur.rowcount != 1:
                return None  # 다른 실행이 먼저 만들었다

        address = client.register_wallet(pubkey)["address"]
        if not address.startswith("bc1"):
            raise PaymentError(f"지갑 주소가 메인넷 bech32 형식이 아닙니다: {address}")
        cur.execute("UPDATE users SET wallet_address = %s WHERE email = %s", (address, email))
    return address


def _instant_jwt(priv_hex: str, pubkey: str) -> str:
    cached = _jwt_cache.get(pubkey)
    if cached and cached[1] > time.monotonic():
        return cached[0]
    challenge = client.get_data_to_sign(pubkey)
    signature = keys.sign_challenge(priv_hex, challenge["messageToSign"])
    token = client.get_jwt(challenge["challengeId"], signature)["accessToken"]
    _jwt_cache[pubkey] = (token, time.monotonic() + JWT_TTL_SECONDS)
    return token


# ---------------------------------------------------------------- 결제

def cad_to_sats(price_minor: int, quantity: int) -> int:
    """CAD 금액(센트 × 수량)을 고정 환율로 sats 로 환산한다. 구매자가 덜 내지 않도록 올림한다."""
    try:
        rate = Decimal(settings.btc_cad_rate)
    except InvalidOperation:
        rate = Decimal(0)
    if rate <= 0:
        raise PaymentError("BTC_CAD_RATE is not configured")
    cad = Decimal(price_minor * quantity) / 100
    return int((cad / rate * SATS_PER_BTC).to_integral_value(rounding=ROUND_UP))


def _load_context(order_id: int) -> dict:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT o.order_id, o.quantity, o.payment_id, o.payment_tx_id, o.buyer_email, s.seller_email, "
            "       p.price_minor, p.currency, p.title, p.merchant_email, "
            "       su.secret AS seller_secret, "
            "       bu.wallet_pubkey, bu.wallet_address, bu.wallet_private_key_enc "
            "FROM purchase_orders o "
            "JOIN products p ON p.id = o.product_id "
            "JOIN stores s ON s.store_id = o.store_id "
            "JOIN users su ON su.email = s.seller_email "
            "LEFT JOIN users bu ON bu.email = o.buyer_email "
            "WHERE o.order_id = %s",
            (order_id,),
        )
        ctx = cur.fetchone()
    if ctx is None:
        raise PaymentError(f"order {order_id} not found")
    if not ctx["buyer_email"]:
        raise PaymentError("주문에 buyer_email 이 없습니다")
    if not ctx["seller_secret"]:
        raise PaymentError("판매자 머천트 설정(API 키)이 없습니다")
    if not (ctx["wallet_private_key_enc"] and ctx["wallet_address"]):
        raise PaymentError("구매자 지갑이 준비되지 않았습니다")
    if ctx["currency"] != "CAD":
        raise PaymentError(f"지원하지 않는 통화입니다: {ctx['currency']}")
    return ctx


def _save_order(order_id: int, **columns) -> None:
    assignments = ", ".join(f"{k} = %s" for k in columns)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"UPDATE purchase_orders SET {assignments}, updated_at = NOW() WHERE order_id = %s",
            [*columns.values(), order_id],
        )


def pay_order(order_id: int) -> None:
    """주문의 구매자→판매자 결제(CUSTOMER_PAYMENT)를 진행하고 payments 테이블에 기록한다. 결제가 확인(paid)되면 정상 반환하고, 아니면 PaymentError 를 던진다.

    재시도해도 이중 결제되지 않도록 단계마다 진행 상태(payment_id, payment_tx_id)를 먼저 저장한다.
    """
    external_id = ledger.external_id_for(order_id, ledger.CUSTOMER_PAYMENT)  # 결제사 멱등키이자 payments 의 식별자
    try:
        ctx = _pay_order(order_id, external_id)
    except PaymentError as e:
        ledger.record_error(external_id, str(e))
        raise
    _record_supplier_payment(ctx)


def _record_supplier_payment(ctx: dict) -> None:
    """구매자→판매자 결제가 확인된 주문에 대해 판매자→공급자 결제(PENDING)를 만든다. 금액은 상품가×수량의 sats 환산."""
    ledger.ensure_supplier_payment(
        order_id=ctx["order_id"],
        payer_email=ctx["seller_email"],
        payee_email=ctx["merchant_email"],
        amount_sats=cad_to_sats(ctx["price_minor"], ctx["quantity"]),
        fiat_amount_minor=ctx["price_minor"] * ctx["quantity"],
        fiat_currency=ctx["currency"],
        exchange_rate=Decimal(settings.btc_cad_rate),
    )


def _pay_order(order_id: int, external_id: str) -> dict:
    ctx = _load_context(order_id)

    # 이미 PSBT 를 제출한 주문은 다시 결제하지 않고 결제 확인만 한다
    if ctx["payment_tx_id"] and ctx["payment_id"]:
        _confirm_paid(external_id, ctx["payment_id"])
        return ctx

    sats = cad_to_sats(ctx["price_minor"], ctx["quantity"])
    if sats < DUST_SATS:
        raise PaymentError(f"결제 금액 {sats} sats 가 최소 금액({DUST_SATS} sats)보다 작습니다")

    seller_key = decrypt(ctx["seller_secret"])
    payment = client.create_payment(
        seller_key,
        Decimal(sats) / SATS_PER_BTC,
        f"{ctx['title']} x{ctx['quantity']} (order #{order_id})"[:200],
        external_id=external_id,  # 멱등키: 같은 주문은 같은 결제를 돌려받는다
    )
    payment_id = payment["paymentId"]
    if int(payment["amountSats"]) != sats:
        raise PaymentError(f"결제 금액 불일치: 요청 {sats} sats, 응답 {payment['amountSats']} sats")
    _save_order(order_id, payment_id=payment_id, amount_sats=sats)

    status = payment["status"]
    ledger.upsert_created(
        order_id=order_id,
        payment_type=ledger.CUSTOMER_PAYMENT,
        external_id=external_id,
        provider_payment_id=payment_id,
        status="COMPLETED" if status == "paid" else "PENDING",
        payer_email=ctx["buyer_email"],
        payee_email=ctx["seller_email"],
        from_address=ctx["wallet_address"],
        to_address=payment["btcAddress"],
        amount_sats=sats,
        fiat_amount_minor=ctx["price_minor"] * ctx["quantity"],
        fiat_currency=ctx["currency"],
        exchange_rate=Decimal(settings.btc_cad_rate),
    )
    if status == "paid":
        ledger.mark_completed(external_id)
        return ctx
    if status != "initiated":
        raise PaymentError(f"결제 상태가 {status} 입니다 (payment_id={payment_id})")

    priv_hex = decrypt(ctx["wallet_private_key_enc"])
    jwt = _instant_jwt(priv_hex, ctx["wallet_pubkey"])
    built = client.build_psbt(jwt, payment_id)
    fee = keys.verify_payment_psbt(built["psbtBase64"], payment["btcAddress"], sats, ctx["wallet_address"], MAX_FEE_SATS)
    signed = keys.sign_psbt(built["psbtBase64"], priv_hex)

    submitted = client.submit_psbt(jwt, payment_id, built["jobId"], signed)
    if not submitted["success"]:
        raise PaymentError(f"PSBT 제출 실패 (payment_id={payment_id})")
    # 응답에 txid 가 없어도 "제출 완료" 표시는 반드시 남겨 재시도 때 다시 결제하지 않게 한다
    tx_id = submitted.get("paymentTxId") or "submitted"
    _save_order(order_id, payment_tx_id=tx_id)
    ledger.mark_processing(external_id, tx_id, fee)

    _confirm_paid(external_id, payment_id)
    return ctx


def _confirm_paid(external_id: str, payment_id: str) -> None:
    status = client.get_payment(payment_id)["status"]
    if status != "paid":
        raise PaymentError(f"결제 확인 대기 중 (status={status}, payment_id={payment_id})")
    ledger.mark_completed(external_id)
