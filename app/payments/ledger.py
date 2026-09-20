"""결제 내역(payments 테이블) 기록. 결제 진행 단계마다 같은 행을 갱신하고, 결제 1건은 (provider, external_id) 로 식별한다."""
from decimal import Decimal

from app.db import get_conn

CUSTOMER_PAYMENT = "CUSTOMER_PAYMENT"
SUPPLIER_PAYMENT = "SUPPLIER_PAYMENT"
PROVIDER = "GOBTCPAY"

# 주문 1건에는 결제가 2건: CUSTOMER_PAYMENT(구매자→판매자), SUPPLIER_PAYMENT(판매자→공급자)
_EXTERNAL_ID_SUFFIX = {CUSTOMER_PAYMENT: "customer", SUPPLIER_PAYMENT: "supplier"}


def external_id_for(order_id: int, payment_type: str) -> str:
    """결제사에 보내는 멱등키이자 payments 의 식별자. 같은 주문의 두 결제가 겹치지 않게 종류를 붙인다."""
    return f"order-{order_id}-{_EXTERNAL_ID_SUFFIX[payment_type]}"


def upsert_created(
    *,
    order_id: int,
    payment_type: str,
    external_id: str,
    provider_payment_id: str,
    status: str,
    payer_email: str | None,
    payee_email: str | None,
    from_address: str | None,
    to_address: str | None,
    amount_sats: int,
    fiat_amount_minor: int | None,
    fiat_currency: str | None,
    exchange_rate: Decimal | None,
) -> None:
    """결제가 생성(또는 멱등 재조회)될 때 기록한다. 이미 진행 중인 행의 상태는 되돌리지 않는다."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO payments (order_id, payment_type, status, payer_email, payee_email, from_address, to_address, "
            "  amount_sats, fiat_amount_minor, fiat_currency, exchange_rate, provider, external_id, provider_payment_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE provider_payment_id = VALUES(provider_payment_id), "
            "  to_address = VALUES(to_address), from_address = VALUES(from_address)",
            (order_id, payment_type, status, payer_email, payee_email, from_address, to_address, amount_sats,
             fiat_amount_minor, fiat_currency, exchange_rate, PROVIDER, external_id, provider_payment_id),
        )


def mark_processing(external_id: str, tx_id: str | None, fee_sats: int | None) -> None:
    """PSBT 제출 완료 (결제 확인 대기)."""
    _update(external_id, "status = 'PROCESSING', tx_id = %s, fee_sats = %s", (tx_id, fee_sats))


def mark_completed(external_id: str) -> None:
    _update(external_id, "status = 'COMPLETED', completed_at = NOW(), failure_reason = NULL", ())


def record_error(external_id: str, reason: str) -> None:
    """가장 최근 실패 사유만 남긴다. 재시도할 때마다 행이 늘지 않는다(행이 아직 없으면 무시)."""
    _update(external_id, "failure_reason = %s", (reason[:1000],))


def _update(external_id: str, assignments: str, params: tuple) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"UPDATE payments SET {assignments} WHERE provider = %s AND external_id = %s",
            (*params, PROVIDER, external_id),
        )


def ensure_supplier_payment(
    *,
    order_id: int,
    payer_email: str | None,
    payee_email: str | None,
    amount_sats: int,
    fiat_amount_minor: int | None,
    fiat_currency: str | None,
    exchange_rate: Decimal | None,
) -> None:
    """구매자→판매자 결제가 끝난 주문에 대해 판매자→공급자 결제(PENDING)를 만든다. 이미 있으면 그대로 둔다.

    payee_email 은 products.merchant_email. 없으면 받는 쪽을 알 수 없으므로 사유를 남겨 둔다.
    실제 지급은 하지 않는다.
    """
    reason = None if payee_email else "공급자 이메일(products.merchant_email)이 없습니다"
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO payments (order_id, payment_type, status, payer_email, payee_email, amount_sats, "
            "  fiat_amount_minor, fiat_currency, exchange_rate, provider, external_id, failure_reason) "
            "VALUES (%s, %s, 'PENDING', %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE id = id",
            (order_id, SUPPLIER_PAYMENT, payer_email, payee_email, amount_sats, fiat_amount_minor, fiat_currency,
             exchange_rate, PROVIDER, external_id_for(order_id, SUPPLIER_PAYMENT), reason),
        )
