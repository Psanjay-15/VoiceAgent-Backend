from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status

from app.config import settings


def hash_password(password: str) -> str:
    try:
        import bcrypt
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="bcrypt is not installed. Run pip install -r requirements.txt.",
        ) from exc
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        import bcrypt
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="bcrypt is not installed. Run pip install -r requirements.txt.",
        ) from exc
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(*, subject: str, email: str) -> str:
    try:
        import jwt
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PyJWT is not installed. Run pip install -r requirements.txt.",
        ) from exc
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_access_token_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        import jwt
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PyJWT is not installed. Run pip install -r requirements.txt.",
        ) from exc
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def get_email_from_token(token: str | None) -> str | None:
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except Exception:
        return None
    email = payload.get("email")
    return str(email).lower() if email else None
