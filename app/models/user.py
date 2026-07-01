from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def new_user_document(*, email: str, password_hash: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "email": email,
        "password_hash": password_hash,
        "created_at": now,
        "updated_at": now,
    }


def public_user(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(document.get("_id")),
        "email": document["email"],
        "created_at": document.get("created_at"),
    }
