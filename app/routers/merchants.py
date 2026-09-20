from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.payments import service
from app.payments.errors import PaymentError

router = APIRouter(prefix="/merchants", tags=["merchants"])


class VerifyEmailRequest(BaseModel):
    code: str


class MerchantSetup(BaseModel):
    email: str
    merchant_id: str | None = None
    xpub: str


@router.post("/{email}/verify-email", response_model=MerchantSetup)
def verify_email(email: str, body: VerifyEmailRequest):
    """이메일로 받은 6자리 인증코드로 머천트를 활성화하고 xpub 연결, API 키 발급까지 한 번에 진행한다."""
    try:
        return service.onboard_merchant(email, body.code)
    except LookupError:
        raise HTTPException(404, "user not found")
    except PaymentError as e:
        raise HTTPException(502, str(e))
