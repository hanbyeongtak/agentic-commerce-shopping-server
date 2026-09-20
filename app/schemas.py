from datetime import datetime

from pydantic import BaseModel


class ProductCreate(BaseModel):
    sku: str
    product_gid: str
    title: str
    vendor: str | None = None
    price_minor: int
    currency: str
    available: bool
    image_url: str | None = None
    product_url: str | None = None
    merchant_name: str | None = None
    merchant_domain: str | None = None
    merchant_id: str | None = None
    merchant_email: str | None = None  # 공급자 이메일 (공급자 결제의 payee_email)
    merchant_url: str | None = None
    store_id: str | None = None


class ProductUpdate(BaseModel):
    sku: str | None = None
    product_gid: str | None = None
    title: str | None = None
    vendor: str | None = None
    price_minor: int | None = None
    currency: str | None = None
    available: bool | None = None
    image_url: str | None = None
    product_url: str | None = None
    merchant_name: str | None = None
    merchant_domain: str | None = None
    merchant_id: str | None = None
    merchant_email: str | None = None
    merchant_url: str | None = None
    store_id: str | None = None


class Product(ProductCreate):
    id: int
    created_at: datetime | None = None
