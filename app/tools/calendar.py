from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from app.config import SERVER_ROOT, settings
from app.core.logging import get_logger

log = get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]


@dataclass
class CalendarResult:
    success: bool
    message: str
    event_link: str | None = None


async def schedule_online_meeting(
    *,
    attendee_email: str,
    summary: str,
    requested_time: str | None = None,
    duration_minutes: int = 30,
    request_id: str | None = None,
) -> CalendarResult:

    if not settings.google_credentials_file:
        log.warning("Google Calendar not configured - missing GOOGLE_CREDENTIALS_FILE")
        return CalendarResult(False, "Google Calendar is not configured.")

    return await asyncio.to_thread(
        _schedule_online_meeting_sync,
        attendee_email=attendee_email,
        summary=summary,
        requested_time=requested_time,
        duration_minutes=duration_minutes,
        request_id=request_id,
    )


def build_google_authorization_url() -> str:
    flow = _build_web_flow()
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    _save_oauth_state(flow)
    return authorization_url


def save_google_oauth_token(callback_url: str) -> None:
    flow = _build_web_flow()
    _restore_oauth_state(flow)
    flow.fetch_token(authorization_response=callback_url)
    token_path = _token_path()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(flow.credentials.to_json(), encoding="utf-8")
    _clear_oauth_state()


def _schedule_online_meeting_sync(
    *,
    attendee_email: str,
    summary: str,
    requested_time: str | None,
    duration_minutes: int,
    request_id: str | None,
) -> CalendarResult:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.errors import HttpError
        from googleapiclient.discovery import build
    except ImportError:
        return CalendarResult(False, "Google Calendar libraries are not installed.")

    creds = None
    token_path = _token_path()
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
        else:
            return CalendarResult(
                False,
                "Google Calendar is not authorized. Open /auth/google/start once.",
            )

    service = build("calendar", "v3", credentials=creds)
    start = _parse_or_default_time(requested_time)
    end = start + timedelta(minutes=duration_minutes)
    body = {
        "summary": "Online real estate consultation",
        "description": summary,
        "start": {"dateTime": start.isoformat(), "timeZone": settings.default_timezone},
        "end": {"dateTime": end.isoformat(), "timeZone": settings.default_timezone},
        "attendees": [{"email": attendee_email}],
        "conferenceData": {
            "createRequest": {
                "requestId": request_id or f"voice-agent-{int(datetime.now().timestamp())}",
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
    }
    if request_id:
        body["id"] = _calendar_event_id(request_id)

    try:
        event = (
            service.events()
            .insert(
                calendarId=settings.google_calendar_id,
                body=body,
                conferenceDataVersion=1,
                sendUpdates="all",
            )
            .execute()
        )
    except HttpError as exc:
        if getattr(exc, "status_code", None) == 409 or getattr(getattr(exc, "resp", None), "status", None) == 409:
            return CalendarResult(True, "Online meeting was already scheduled.")
        raise
    link = event.get("hangoutLink") or event.get("htmlLink")
    return CalendarResult(True, "Online meeting scheduled.", link)


def _calendar_event_id(request_id: str) -> str:
    digest = hashlib.sha1(request_id.encode("utf-8")).hexdigest()
    return f"va{digest[:24]}"


def _parse_or_default_time(value: str | None) -> datetime:
    tz = ZoneInfo(settings.default_timezone)
    if value:
        with_tz = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(with_tz)
            return parsed.astimezone(tz) if parsed.tzinfo else parsed.replace(tzinfo=tz)
        except ValueError:
            log.info("Could not parse requested meeting time: %s", value)
        natural = _parse_natural_meeting_time(value, tz)
        if natural is not None:
            return natural

    now = datetime.now(tz)
    tomorrow = now + timedelta(days=1)
    return tomorrow.replace(hour=11, minute=0, second=0, microsecond=0)


def _parse_natural_meeting_time(value: str, tz: ZoneInfo) -> datetime | None:
    lower = value.lower()
    explicit_date = _parse_numeric_date(lower, tz) or _parse_month_name_date(lower, tz)
    if explicit_date is not None:
        hour, minute = _parse_natural_time(lower)
        return explicit_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    now = datetime.now(tz)
    day = None
    for name, index in weekdays.items():
        if name in lower:
            days_ahead = (index - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            day = now + timedelta(days=days_ahead)
            break
    if day is None:
        if "tomorrow" in lower:
            day = now + timedelta(days=1)
        elif "today" in lower:
            day = now
        elif _has_natural_time(lower):
            hour, minute = _parse_natural_time(lower)
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return candidate if candidate > now else candidate + timedelta(days=1)
        else:
            return None

    hour, minute = _parse_natural_time(lower)
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _parse_numeric_date(lower: str, tz: ZoneInfo) -> datetime | None:
    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", lower)
    if not match:
        return None
    month = int(match.group(1))
    day = int(match.group(2))
    year = int(match.group(3)) if match.group(3) else datetime.now(tz).year
    if year < 100:
        year += 2000
    try:
        return datetime(year, month, day, tzinfo=tz)
    except ValueError:
        log.info("Could not parse numeric meeting date: %s", match.group(0))
        return None


def _parse_month_name_date(lower: str, tz: ZoneInfo) -> datetime | None:
    months = {
        "january": 1,
        "jan": 1,
        "february": 2,
        "feb": 2,
        "march": 3,
        "mar": 3,
        "april": 4,
        "apr": 4,
        "may": 5,
        "june": 6,
        "jun": 6,
        "july": 7,
        "jul": 7,
        "august": 8,
        "aug": 8,
        "september": 9,
        "sep": 9,
        "sept": 9,
        "october": 10,
        "oct": 10,
        "november": 11,
        "nov": 11,
        "december": 12,
        "dec": 12,
    }
    names = "|".join(sorted(months, key=len, reverse=True))
    match = re.search(
        rf"\b({names})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{2,4}}))?\b",
        lower,
    )
    if not match:
        return None
    month = months[match.group(1)]
    day = int(match.group(2))
    year = int(match.group(3)) if match.group(3) else datetime.now(tz).year
    if year < 100:
        year += 2000
    try:
        return datetime(year, month, day, tzinfo=tz)
    except ValueError:
        log.info("Could not parse month-name meeting date: %s", match.group(0))
        return None


def _parse_natural_time(lower: str) -> tuple[int, int]:
    if "noon" in lower:
        return 12, 0
    match = re.search(r"\b([01]?\d|2[0-3])(?::([0-5]\d))?\s*(am|pm)\b", lower)
    if not match:
        match = re.search(r"\bat\s+([01]?\d|2[0-3])(?::([0-5]\d))?\b", lower)
    if not match:
        return 11, 0
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    suffix = match.group(3) if len(match.groups()) >= 3 else None
    if suffix == "pm" and hour < 12:
        hour += 12
    elif suffix == "am" and hour == 12:
        hour = 0
    elif suffix is None and hour == 12:
        hour = 12
    return hour, minute


def _has_natural_time(lower: str) -> bool:
    return "noon" in lower or bool(re.search(r"\b([01]?\d|2[0-3])(?::([0-5]\d))?\s*(am|pm)\b", lower))


def _build_web_flow():
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError as exc:
        raise RuntimeError("Google OAuth libraries are not installed.") from exc

    credentials_path = _credentials_path()
    if not credentials_path.exists():
        raise RuntimeError(f"Google credentials file not found: {credentials_path}")

    _allow_localhost_http_for_dev(settings.google_redirect_uri)
    flow = Flow.from_client_secrets_file(str(credentials_path), scopes=SCOPES)
    flow.redirect_uri = settings.google_redirect_uri
    return flow


def _allow_localhost_http_for_dev(redirect_uri: str) -> None:
    parsed = urlparse(redirect_uri)
    if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}:
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")


def _credentials_path() -> Path:
    if not settings.google_credentials_file:
        raise RuntimeError("GOOGLE_CREDENTIALS_FILE is not set.")
    return _resolve_server_path(settings.google_credentials_file)


def _token_path() -> Path:
    return _resolve_server_path(settings.google_token_file or "token.json")


def _oauth_state_path() -> Path:
    return SERVER_ROOT / ".google_oauth_state.json"


def _save_oauth_state(flow) -> None:
    state = getattr(flow.oauth2session, "_state", None)
    payload = {
        "state": state,
        "code_verifier": getattr(flow, "code_verifier", None),
    }
    _oauth_state_path().write_text(json.dumps(payload), encoding="utf-8")


def _restore_oauth_state(flow) -> None:
    state_path = _oauth_state_path()
    if not state_path.exists():
        return
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    if payload.get("code_verifier"):
        flow.code_verifier = payload["code_verifier"]
    if payload.get("state"):
        flow.oauth2session._state = payload["state"]


def _clear_oauth_state() -> None:
    with contextlib.suppress(Exception):
        _oauth_state_path().unlink()


def _resolve_server_path(value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return SERVER_ROOT / path
