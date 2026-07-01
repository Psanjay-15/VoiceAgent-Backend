from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_client: Any = None
_db: Any = None


async def connect_to_mongo() -> None:
    global _client, _db
    if not settings.mongodb_uri:
        log.warning("MongoDB not configured - MONGODB_URI is empty")
        return

    from motor.motor_asyncio import AsyncIOMotorClient

    _client = AsyncIOMotorClient(settings.mongodb_uri)
    _db = _client[settings.mongodb_db_name]
    await _db.users.create_index("email", unique=True)
    log.info("MongoDB connected (db=%s)", settings.mongodb_db_name)


async def close_mongo_connection() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None


def get_database():
    if _db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MongoDB is not connected. Set MONGODB_URI and restart the server.",
        )
    return _db


def users_collection():
    return get_database().users
