from __future__ import annotations

import json
import re

from app.agent.actions.llm_utils import collect_reply
from app.agent.turn_intent.models import TurnIntentResult
from app.agent.turn_intent.prompts import TURN_INTENT_PROMPT
from app.core.logging import get_logger
from app.llm.base import Message
from app.llm.factory import get_llm_provider

log = get_logger(__name__)


class TurnIntentClassifier:
    def __init__(self) -> None:
        self._provider = get_llm_provider()

    async def classify(self, history: list[Message], latest_user_text: str) -> TurnIntentResult:
        messages = [
            {"role": "system", "content": TURN_INTENT_PROMPT},
            {"role": "user", "content": _format_classification_context(history, latest_user_text)},
        ]
        try:
            raw = await collect_reply(self._provider, messages)
            return _parse_result(raw)
        except Exception as exc:
            log.warning("turn intent classification failed: %s", exc)
            return TurnIntentResult(intent="continue_conversation", confidence=0.0, reason="classifier_failed")


def _format_classification_context(history: list[Message], latest_user_text: str) -> str:
    recent = history[-6:]
    rows = []
    for item in recent:
        role = "Agent" if item["role"] == "assistant" else "Caller"
        rows.append(f"{role}: {item['content']}")
    rows.append(f"Latest caller utterance: {latest_user_text}")
    return "\n".join(rows)


def _parse_result(raw: str) -> TurnIntentResult:
    try:
        data = json.loads(_extract_json(raw))
    except (json.JSONDecodeError, TypeError):
        log.warning("Could not parse turn intent JSON: %r", raw)
        return TurnIntentResult(intent="continue_conversation", confidence=0.0, reason="invalid_json")

    intent = data.get("intent")
    if intent not in {"continue_conversation", "end_conversation"}:
        intent = "continue_conversation"

    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    confidence = max(0.0, min(confidence, 1.0))
    return TurnIntentResult(
        intent=intent,
        confidence=confidence,
        reason=str(data.get("reason") or ""),
    )


def _extract_json(raw: str) -> str:
    match = re.search(r"\{.*\}", raw, flags=re.S)
    return match.group(0) if match else raw
