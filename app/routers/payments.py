from datetime import datetime
from enum import Enum

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app import crud

router = APIRouter(prefix="/payments", tags=["payments"])


# 주문 1건에는 결제가 2건(종류별 1건씩)이며, 주문의 두 결제는 GET /payments?order_id= 로 함께 조회한다.
class PaymentType(str, Enum):
    CUSTOMER_PAYMENT = "CUSTOMER_PAYMENT"  # 구매자 → 판매자
    SUPPLIER_PAYMENT = "SUPPLIER_PAYMENT"  # 판매자 → 공급자


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Payment(BaseModel):
    id: int
    order_id: int | None = None
    payment_type: PaymentType
    status: PaymentStatus
    payer_email: str | None = None
    payee_email: str | None = None
    from_address: str | None = None
    to_address: str | None = None
    amount_sats: int
    fee_sats: int | None = None
    fiat_amount_minor: int | None = None
    fiat_currency: str | None = None
    exchange_rate: float | None = None
    provider: str
    external_id: str
    provider_payment_id: str | None = None
    tx_id: str | None = None
    failure_reason: str | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


@router.get("", response_model=list[Payment])
def list_payments(
    order_id: int | None = None,
    payment_type: PaymentType | None = None,
    status: PaymentStatus | None = None,
    payer_email: str | None = None,
    payee_email: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    filters = {
        "order_id": order_id,
        "payment_type": payment_type.value if payment_type else None,
        "status": status.value if status else None,
        "payer_email": payer_email,
        "payee_email": payee_email,
    }
    return crud.fetch_all("payments", "id", limit, offset, filters)


@router.get("/{payment_id}", response_model=Payment)
def get_payment(payment_id: int):
    return crud.fetch_one("payments", "id", payment_id)
