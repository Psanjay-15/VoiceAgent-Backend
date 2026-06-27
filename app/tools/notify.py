from __future__ import annotations

from app.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)
_PUSHOVER_URL = "https://api.pushover.net/1/messages.json"


async def send_push(message: str, title: str = "Voice Agent") -> bool:
    """Push a notification to the admin via Pushover. No-op (logs) if not configured."""
    if not (settings.pushover_token and settings.pushover_user):
        log.warning("Pushover not configured — skipping push %r", title)
        return False
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                _PUSHOVER_URL,
                data={
                    "token": settings.pushover_token,
                    "user": settings.pushover_user,
                    "title": title,
                    "message": message,
                },
            )
        if r.status_code != 200:
            log.warning("Pushover failed: %s %s", r.status_code, r.text[:200])
            return False
        return True
    except Exception as e:
        log.warning("Pushover error: %s", e)
        return False
