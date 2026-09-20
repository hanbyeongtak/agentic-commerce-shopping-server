from datetime import datetime
from enum import Enum

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

from app import crud
from app.security import hash_password

router = APIRouter(prefix="/users", tags=["users"])


class UserType(str, Enum):
    BUYER = "BUYER"
    SELLER = "SELLER"


class UserCreate(BaseModel):
    email: str
    password: str
    user_type: UserType
    address: str


class UserUpdate(BaseModel):
    password: str | None = None
    user_type: UserType | None = None
    address: str | None = None


class User(BaseModel):
    email: str
    user_type: UserType
    address: str
    created_at: datetime | None = None
    # 결제 관련 (비밀이 아닌 값만 노출: 개인키/니모닉/API 키/토큰은 응답에 포함하지 않는다)
    user_id: str | None = None
    merchant_id: str | None = None
    merchant_xpub: str | None = None
    wallet_address: str | None = None  # 구매자가 BTC 를 입금할 주소


@router.get("", response_model=list[User])
def list_users(
    user_type: UserType | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    filters = {"user_type": user_type.value if user_type else None}
    return crud.fetch_all("users", "created_at", limit, offset, filters)


@router.get("/{email}", response_model=User)
def get_user(email: str):
    return crud.fetch_one("users", "email", email)


@router.post("", response_model=User, status_code=201)
def create_user(body: UserCreate):
    data = body.model_dump(mode="json")
    data["password"] = hash_password(body.password)
    crud.insert("users", data)
    return crud.fetch_one("users", "email", body.email)


@router.patch("/{email}", response_model=User)
def update_user(email: str, body: UserUpdate):
    data = body.model_dump(mode="json", exclude_unset=True)
    if data.get("password") is not None:
        data["password"] = hash_password(data["password"])
    crud.update("users", "email", email, data)
    return crud.fetch_one("users", "email", email)


@router.delete("/{email}", status_code=204)
def delete_user(email: str):
    crud.delete("users", "email", email)
    return Response(status_code=204)
