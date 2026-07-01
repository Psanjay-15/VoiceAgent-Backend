from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, status

from app.db.mongodb import users_collection
from app.models.user import new_user_document, public_user
from app.services.security import hash_password, verify_password

_EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.I)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_email(email: str) -> str:
    normalized = normalize_email(email)
    if not _EMAIL_RE.match(normalized):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Please provide a valid email address.",
        )
    return normalized


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters.",
        )


async def create_user(*, email: str, password: str) -> dict[str, Any]:
    normalized_email = validate_email(email)
    validate_password(password)
    document = new_user_document(
        email=normalized_email,
        password_hash=hash_password(password),
    )
    try:
        result = await users_collection().insert_one(document)
    except Exception as exc:
        if exc.__class__.__name__ == "DuplicateKeyError":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            ) from exc
        raise
    document["_id"] = result.inserted_id
    return document


async def authenticate_user(*, email: str, password: str) -> dict[str, Any] | None:
    document = await users_collection().find_one({"email": validate_email(email)})
    if not document:
        return None
    if not verify_password(password, document["password_hash"]):
        return None
    return document


def to_public_user(document: dict[str, Any]) -> dict[str, Any]:
    return public_user(document)
