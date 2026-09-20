from cryptography.fernet import Fernet, InvalidToken

from app.config import settings
from app.payments.errors import PaymentError


def _fernet() -> Fernet:
    if not settings.encryption_key:
        raise PaymentError("ENCRYPTION_KEY is not configured")
    return Fernet(settings.encryption_key.encode())


def encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        raise PaymentError("Failed to decrypt stored secret (ENCRYPTION_KEY mismatch?)")
