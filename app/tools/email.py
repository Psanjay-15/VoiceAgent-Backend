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
    msg["To"] = "sspandere26@gmail.com"
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        await asyncio.to_thread(_send_sync, msg)
        return True
    except Exception as e:
        log.warning("SMTP error sending to %s: %s", to, e)
        return False


def _send_sync(msg: EmailMessage) -> None:
    import smtplib

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as s:
        s.starttls()
        s.login(settings.smtp_user, settings.smtp_password)
        s.send_message(msg)
