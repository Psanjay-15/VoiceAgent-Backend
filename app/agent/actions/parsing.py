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
    if action not in {"in_person_meet", "online_meet", "send_material", "none"}:
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
        "material_type": data.get("material_type"),
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
    if pending_material_email(history) and extract_email(question):
        return "send_material"
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
            "schedule meeting",
            "schedule a meeting",
            "calendar meeting",
            "meeting calendar",
            "calendar invite",
            "meet with admin",
            "meeting with admin",
            "appointment with admin",
            "book a meeting",
            "book meeting",
        )
    ):
        return "online_meet"
    if any(phrase in lower for phrase in ("brochure", "catalogue", "catalog", "contact details", "email me", "send details")):
        return "send_material"
    return "none"


def latest_turn_supports_action(history: list[Message], question: str, action: ActionType) -> bool:
    if action == "online_meet":
        return fallback_action(history, question) == "online_meet"
    if action == "send_material":
        return fallback_action(history, question) == "send_material"
    if action == "in_person_meet":
        return fallback_action(history, question) == "in_person_meet"
    return False


def pending_online_email(history: list[Message]) -> bool:
    return last_assistant_contains(history, "what email address should i send the invite to")


def has_pending_meeting_request(history: list[Message]) -> bool:
    return any(
        item["role"] == "assistant"
        and (
            "calendar meeting" in item["content"].lower()
            or "meeting email" in item["content"].lower()
            or "send the invite" in item["content"].lower()
        )
        for item in history[-6:]
    )


def pending_material_email(history: list[Message]) -> bool:
    return last_assistant_contains(history, "what email address should i use")


def pending_in_person_details(history: list[Message]) -> bool:
    return last_assistant_contains(history, "preferred area and time")


def last_assistant_contains(history: list[Message], needle: str) -> bool:
    for item in reversed(history):
        if item["role"] != "assistant":
            continue
        return needle in item["content"].lower()
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
