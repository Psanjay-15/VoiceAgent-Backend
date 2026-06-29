from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.agent.actions.models import ActionType
from app.core.logging import get_logger
from app.llm.base import Message

log = get_logger(__name__)


def format_transcript(history: list[Message], question: str) -> str:
    rows = []
    for item in history:
        role = "Agent" if item["role"] == "assistant" else "Caller"
        rows.append(f"{role}: {item['content']}")
    if question:
        rows.append(f"Caller: {question}")
    return "\n".join(rows)


def parse_decision(raw: str, history: list[Message], question: str) -> dict[str, Any]:
    try:
        data = json.loads(_extract_json(raw))
    except (json.JSONDecodeError, TypeError):
        log.warning("Could not parse action decision JSON: %r", raw)
        data = {}

    transcript = format_transcript(history, question)
    email = normalize_email(data.get("email") or extract_email(question) or extract_email(transcript))
    action = data.get("action") or "none"
    if action not in {"admin_followup", "in_person_meet", "online_meet", "none"}:
        action = "none"

    fallback = fallback_action(history, question)
    if fallback != "none":
        action = fallback
    elif action != "none" and not latest_turn_supports_action(history, question, action):
        action = "none"

    return {
        "action": action,
        "email": email,
        "requested_time": data.get("requested_time"),
        "summary": data.get("summary") or question,
    }


def extract_email(text: str) -> str | None:
    matches = re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, flags=re.I)
    return matches[-1] if matches else None


def normalize_email(email: str | None) -> str | None:
    return email.lower().strip(".,;:!?") if email else None


def fallback_action(history: list[Message], question: str) -> ActionType:
    lower = question.lower()
    if pending_online_email(history) and extract_email(question):
        return "online_meet"
    if has_pending_meeting_request(history) and looks_like_meeting_detail(lower):
        return "online_meet"
    if has_pending_meeting_request(history) and any(phrase in lower for phrase in ("go ahead", "schedule it", "send invite")):
        return "online_meet"
    if pending_in_person_details(history) and looks_like_meeting_detail(lower):
        return "in_person_meet"
    if any(
        phrase in lower
        for phrase in (
            "site visit",
            "in person",
            "in-person",
            "visit your office",
            "property visit",
            "we can meet",
            "meet at",
        )
    ):
        return "in_person_meet"
    if any(
        phrase in lower
        for phrase in (
            "online meet",
            "online meeting",
            "video call",
            "google meet",
            "zoom",
            "schedule meet",
            "schedule a meet",
            "schedule calendar meet",
            "schedule a calendar meet",
            "schedule meeting",
            "schedule a meeting",
            "calendar meet",
            "calendar meeting",
            "meeting calendar",
            "calendar invite",
            "schedule call",
            "schedule a call",
            "book a call",
            "call with admin",
            "call with an admin",
            "admin call",
            "meet with admin",
            "meeting with admin",
            "appointment with admin",
            "book a meeting",
            "book meeting",
        )
    ):
        return "online_meet"
    if any(
        phrase in lower
        for phrase in (
            "admin contact",
            "admin details",
            "contact details",
            "contact detail",
            "contact admin",
            "admin phone",
            "admin email",
            "team contact",
            "talk to admin",
            "speak to admin",
            "human follow up",
            "human follow-up",
        )
    ):
        return "admin_followup"
    return "none"


def should_classify_business_action(history: list[Message], question: str) -> bool:
    if fallback_action(history, question) != "none":
        return True
    lower = question.lower()
    if "@" in question and has_pending_meeting_request(history):
        return True
    return any(
        phrase in lower
        for phrase in (
            "meet",
            "meeting",
            "appointment",
            "calendar",
            "call",
            "invite",
            "admin",
            "contact",
            "email",
            "visit",
        )
    )


def latest_turn_supports_action(history: list[Message], question: str, action: ActionType) -> bool:
    if action == "online_meet":
        return fallback_action(history, question) == "online_meet"
    if action == "in_person_meet":
        return fallback_action(history, question) == "in_person_meet"
    if action == "admin_followup":
        return fallback_action(history, question) == "admin_followup"
    return False


def pending_online_email(history: list[Message]) -> bool:
    return last_assistant_contains_any(
        history,
        (
            "what email address should i send the invite to",
            "please share your email",
            "share your email",
            "what email should i use",
            "send the invite",
        ),
    )


def has_pending_meeting_request(history: list[Message]) -> bool:
    return any(
        item["role"] == "assistant"
        and (
            "calendar meeting" in item["content"].lower()
            or "meeting email" in item["content"].lower()
            or "send the invite" in item["content"].lower()
            or "schedule the meeting" in item["content"].lower()
            or "schedule a call" in item["content"].lower()
            or "date and time" in item["content"].lower()
        )
        for item in history[-6:]
    )


def pending_in_person_details(history: list[Message]) -> bool:
    return last_assistant_contains(history, "preferred area and time")


def last_assistant_contains(history: list[Message], needle: str) -> bool:
    return last_assistant_contains_any(history, (needle,))


def last_assistant_contains_any(history: list[Message], needles: tuple[str, ...]) -> bool:
    for item in reversed(history):
        if item["role"] != "assistant":
            continue
        lower = item["content"].lower()
        return any(needle in lower for needle in needles)
    return False


def looks_like_meeting_detail(lower: str) -> bool:
    return any(
        word in lower
        for word in (
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
            "today",
            "tomorrow",
            "noon",
            "morning",
            "evening",
            "am",
            "pm",
            "andheri",
            "bandra",
            "mumbai",
            "office",
            "site",
        )
    )


def _extract_json(raw: str) -> str:
    match = re.search(r"\{.*\}", raw, flags=re.S)
    return match.group(0) if match else raw
