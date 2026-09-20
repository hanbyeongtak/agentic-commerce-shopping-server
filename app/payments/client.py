"""GoBTC Pay HTTP 클라이언트. 인증/서명/DB 는 다루지 않고 API 호출만 한다."""
import json
from decimal import Decimal

import httpx

from app.config import settings
from app.payments.errors import PaymentError

TIMEOUT = 30


def _unwrap(resp: httpx.Response) -> dict:
    """응답에서 payload 를 꺼낸다. 문서상 envelope({"result": {"$case": ...}}) 와 평면 응답을 모두 처리한다."""
    path = resp.request.url.path
    if resp.status_code >= 400:
        raise PaymentError(f"{path} -> HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        body = resp.json()
    except ValueError:
        raise PaymentError(f"{path} -> invalid JSON response")
    if not isinstance(body, dict):
        raise PaymentError(f"{path} -> unexpected response")

    result = body.get("result")
    if isinstance(result, dict) and "$case" in result:
        if result["$case"] != "success":
            raise PaymentError(f"{path} -> failure: {json.dumps(result)[:300]}")
        payload = result.get("success", result)
        return {k: v for k, v in payload.items() if k != "$case"}
    return body


def _post(path: str, *, token: str | None = None, json_body: dict | None = None, content: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = httpx.post(
            settings.gobtcpay_base_url + path,
            headers=headers,
            json=json_body if content is None else None,
            content=content,
            timeout=TIMEOUT,
        )
    except httpx.HTTPError as e:
        raise PaymentError(f"{path} -> request failed: {type(e).__name__}: {e}")
    return _unwrap(resp)


def _require(payload: dict, *keys: str) -> None:
    missing = [k for k in keys if k not in payload]
    if missing:
        raise PaymentError(f"response is missing {missing}")


# ---- Part 1: 판매자 ----
def verify_email(email: str, code: str) -> dict:
    payload = _post("/merchant/auth/verify-email", json_body={"email": email, "code": code})
    _require(payload, "accessToken")
    return payload


def link_xpub(access_token: str, xpub: str, derivation_path: str, master_fingerprint: str, label: str) -> None:
    _post(
        "/merchant/auth/xpub/link-authorized",
        token=access_token,
        json_body={
            "xpub": xpub,
            "derivationPath": derivation_path,
            "masterFingerprint": master_fingerprint,
            "label": label,
        },
    )


def create_api_key(access_token: str, label: str) -> dict:
    """{"type", "prefix", "secret"} 반환. secret 은 이때 한 번만 보인다. storeId 는 절대 넘기지 않는다."""
    payload = _post("/merchant/api-key/create", token=access_token, json_body={"label": label, "type": "secret"})
    api_key = payload.get("apiKey", payload)
    _require(api_key, "secret")
    return api_key


# ---- Part 2: 구매자 ----
def register_wallet(user_pubkey_hex: str) -> dict:
    payload = _post("/instant/wallet/register", json_body={"userPubKeyHex": user_pubkey_hex})
    _require(payload, "address")
    return payload


def get_data_to_sign(user_pubkey_hex: str) -> dict:
    payload = _post("/instant/auth/get-data-to-sign", json_body={"userPubKeyHex": user_pubkey_hex})
    _require(payload, "challengeId", "messageToSign")
    return payload


def get_jwt(challenge_id: str, signature_hex: str) -> dict:
    payload = _post("/instant/auth/get-jwt", json_body={"challengeId": challenge_id, "signature": signature_hex})
    _require(payload, "accessToken")
    return payload


# ---- Part 3: 결제 ----
def create_payment(secret_key: str, amount_btc: Decimal, description: str, external_id: str) -> dict:
    # amount 는 BTC 소수 숫자다. float 로 직렬화하면 5.46e-06 같은 표기가 될 수 있어 고정 소수점으로 직접 끼워 넣는다.
    rest = json.dumps({"currency": "BTC", "description": description, "externalId": external_id})
    body = '{"amount": ' + format(amount_btc, "f") + ", " + rest[1:]
    payload = _post("/merchant/payment/create", token=secret_key, content=body)
    _require(payload, "paymentId", "status", "amountSats", "btcAddress")
    return payload


def build_psbt(instant_jwt: str, payment_id: str) -> dict:
    payload = _post(
        "/instant/psbt/build-transaction-to-sign-payment", token=instant_jwt, json_body={"paymentId": payment_id}
    )
    _require(payload, "jobId", "psbtBase64")
    return payload


def submit_psbt(instant_jwt: str, payment_id: str, job_id: str, signed_psbt_b64: str) -> dict:
    # build 는 /instant/psbt/, submit 은 /instant/transaction/ 아래다 (경로가 다르면 404)
    payload = _post(
        "/instant/transaction/pay-and-sign-pre-authorized-transaction",
        token=instant_jwt,
        json_body={"paymentId": payment_id, "jobId": job_id, "signedPsbtBase64": signed_psbt_b64},
    )
    _require(payload, "success")
    return payload


def get_payment(payment_id: str) -> dict:
    """인증 불필요."""
    payload = _post("/merchant/payment/get", json_body={"paymentId": payment_id})
    _require(payload, "status")
    return payload
