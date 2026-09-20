from datetime import datetime
from enum import Enum

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, Field

from app import crud

router = APIRouter(prefix="/orders", tags=["purchase_orders"])


class DeliveryStatus(str, Enum):
    PENDING = "PENDING" #대기중
    PROCESSING = "PROCESSING" #처리중
    SHIPPED = "SHIPPED" #배송중
    DELIVERED = "DELIVERED" #배송완료
    CANCELLED = "CANCELLED" #취소
    CUSTOMER_PAYMENT_PENDING = "CUSTOMER_PAYMENT_PENDING"
    CUSTOMER_PAYMENT_COMPLETED = "CUSTOMER_PAYMENT_COMPLETED"
    CUSTOMER_PAYMENT_CANCELLED = "CUSTOMER_PAYMENT_CANCELLED"
    SUPPLIER_PAYMENT_PENDING = "SUPPLIER_PAYMENT_PENDING"
    SUPPLIER_PAYMENT_PROCESSING = "SUPPLIER_PAYMENT_PROCESSING"
    SUPPLIER_PAYMENT_COMPLETED = "SUPPLIER_PAYMENT_COMPLETED"

class OrderCreate(BaseModel):
    store_id: int
    product_id: int
    quantity: int = Field(gt=0)
    delivery_status: DeliveryStatus = DeliveryStatus.CUSTOMER_PAYMENT_PENDING
    margin_rate: float | None = Field(default=None, ge=0, le=999.99)
    buyer_email: str | None = None  # 결제할 구매자. 없으면 결제 배치가 처리하지 않는다


class OrderUpdate(BaseModel):
    store_id: int | None = None
    product_id: int | None = None
    quantity: int | None = Field(default=None, gt=0)
    delivery_status: DeliveryStatus | None = None
    margin_rate: float | None = Field(default=None, ge=0, le=999.99)
    buyer_email: str | None = None


class Order(OrderCreate):
    order_id: int
    ordered_at: datetime | None = None
    updated_at: datetime | None = None
    created_at: datetime | None = None
    payment_id: str | None = None
    payment_tx_id: str | None = None
    amount_sats: int | None = None


@router.get("", response_model=list[Order])
def list_orders(
    store_id: int | None = None,
    product_id: int | None = None,
    delivery_status: DeliveryStatus | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    filters = {
        "store_id": store_id,
        "product_id": product_id,
        "delivery_status": delivery_status.value if delivery_status else None,
    }
    return crud.fetch_all("purchase_orders", "order_id", limit, offset, filters)


@router.get("/{order_id}", response_model=Order)
def get_order(order_id: int):
    return crud.fetch_one("purchase_orders", "order_id", order_id)


@router.post("", response_model=Order, status_code=201)
def create_order(body: OrderCreate):
    order_id = crud.insert("purchase_orders", body.model_dump(mode="json"))
    return crud.fetch_one("purchase_orders", "order_id", order_id)


@router.patch("/{order_id}", response_model=Order)
def update_order(order_id: int, body: OrderUpdate):
    crud.update(
        "purchase_orders", "order_id", order_id, body.model_dump(mode="json", exclude_unset=True), touch="updated_at"
    )
    return crud.fetch_one("purchase_orders", "order_id", order_id)


@router.delete("/{order_id}", status_code=204)
def delete_order(order_id: int):
    crud.delete("purchase_orders", "order_id", order_id)
    return Response(status_code=204)
