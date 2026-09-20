from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app import crud
from app.config import settings
from app.db import get_conn
from app.routers.users import User
from app.security import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer()

ALGORITHM = "HS256"
# 존재하지 않는 이메일도 동일한 해시 검증 시간을 쓰도록 하는 더미 값 (계정 존재 여부 노출 방지)
_DUMMY_HASH = hash_password("dummy")


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


def _create_token(email: str, user_type: str) -> str:
    if not settings.jwt_secret:
        raise HTTPException(500, "JWT_SECRET is not configured")
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": email, "user_type": user_type, "exp": exp}, settings.jwt_secret, algorithm=ALGORITHM)


def get_current_user(cred: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    try:
        payload = jwt.decode(cred.credentials, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")
    return crud.fetch_one("users", "email", payload["sub"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT email, password, user_type FROM users WHERE email = %s", (body.email,))
        user = cur.fetchone()

    ok = verify_password(body.password, user["password"] if user else _DUMMY_HASH)
    if not user or not ok:
        raise HTTPException(401, "Invalid email or password")

    return TokenResponse(
        access_token=_create_token(user["email"], user["user_type"]),
        expires_in=settings.jwt_expire_minutes * 60,
    )


@router.get("/me", response_model=User)
def me(user: dict = Depends(get_current_user)):
    return user
