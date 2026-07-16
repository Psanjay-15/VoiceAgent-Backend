from __future__ import annotations
import asyncio
from email.message import EmailMessage

from app.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


async def send_email(to: str, subject: str, body: str) -> bool:
    """Send an email over SMTP. No-op (logs) if SMTP isn't configured."""
    if not (settings.smtp_host and settings.smtp_user and settings.smtp_password):
        log.warning("SMTP not configured — skipping email to %s (%r)", to, subject)
        return False

    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        log.info("sending SMTP email to=%s subject=%r host=%s port=%s", to, subject, settings.smtp_host, settings.smtp_port)
        await asyncio.wait_for(
            asyncio.to_thread(_send_sync, msg),
            timeout=settings.smtp_timeout_seconds + 5,
        )
        return True
    except asyncio.TimeoutError:
        log.warning(
            "SMTP timeout sending to %s after %s seconds",
            to,
            settings.smtp_timeout_seconds + 5,
        )
        return False
    except Exception as e:
        log.warning("SMTP error sending to %s: %s", to, e)
        return False


def _send_sync(msg: EmailMessage) -> None:
    import smtplib

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds) as s:
        s.starttls()
        s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(msg)
