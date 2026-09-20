from datetime import datetime
from enum import Enum
from typing import Literal

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, Field

from app import crud

router = APIRouter(prefix="/stores", tags=["stores"])


class StoreStatus(str, Enum):
    OPEN = "OPEN"
    SUSPENDED = "SUSPENDED"


# 자동업데이트 주기(일): 1일, 7일, 30일
AutoUpdateInterval = Literal[1, 7, 30]


class StoreCreate(BaseModel):
    seller_email: str
    store_name: str
    category: str
    status: StoreStatus = StoreStatus.OPEN
    margin_rate: float = Field(default=0, ge=0, le=999.99)
    auto_update_enabled: bool = False
    auto_update_interval_days: AutoUpdateInterval = 1


class StoreUpdate(BaseModel):
    seller_email: str | None = None
    store_name: str | None = None
    category: str | None = None
    status: StoreStatus | None = None
    margin_rate: float | None = Field(default=None, ge=0, le=999.99)
    auto_update_enabled: bool | None = None
    auto_update_interval_days: AutoUpdateInterval | None = None


class Store(StoreCreate):
    store_id: int
    margin_rate: float | None = None  # 컬럼이 NULL 허용이라 응답에서는 None 가능
    created_at: datetime | None = None


@router.get("", response_model=list[Store])
def list_stores(
    seller_email: str | None = None,
    status: StoreStatus | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    filters = {"seller_email": seller_email, "status": status.value if status else None}
    return crud.fetch_all("stores", "store_id", limit, offset, filters)


@router.get("/{store_id}", response_model=Store)
def get_store(store_id: int):
    return crud.fetch_one("stores", "store_id", store_id)


@router.post("", response_model=Store, status_code=201)
def create_store(body: StoreCreate):
    store_id = crud.insert("stores", body.model_dump(mode="json"))
    return crud.fetch_one("stores", "store_id", store_id)


@router.patch("/{store_id}", response_model=Store)
def update_store(store_id: int, body: StoreUpdate):
    crud.update("stores", "store_id", store_id, body.model_dump(mode="json", exclude_unset=True))
    return crud.fetch_one("stores", "store_id", store_id)


@router.delete("/{store_id}", status_code=204)
def delete_store(store_id: int):
    crud.delete("stores", "store_id", store_id)
    return Response(status_code=204)
