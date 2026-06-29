from __future__ import annotations

import asyncio
import uuid
from typing import Any, Optional

from app.agent.actions.email_state import ConversationEmailState
from app.agent.actions.executor import QueuedActionExecutor
from app.agent.actions.graph import build_business_action_graph
from app.agent.actions.llm_utils import collect_reply
from app.agent.actions.models import ActionResult, ActionState, ActionType
from app.agent.actions.parsing import (
    extract_email,
    fallback_action,
    format_transcript,
    normalize_email,
    parse_decision,
    should_classify_business_action,
)
from app.agent.actions.prompts import ACTION_CLASSIFIER_PROMPT
from app.core.logging import get_logger
from app.llm.base import Message
from app.llm.factory import get_llm_provider

log = get_logger(__name__)


class BusinessActionAgent:
    """LangGraph router for agentic business actions around the voice conversation."""

    def __init__(self) -> None:
        self._provider = get_llm_provider()
        self._graph = build_business_action_graph(
            decide=self._decide,
            route=self._route,
            admin_followup=self._handle_admin_followup,
            in_person=self._handle_in_person,
            online=self._handle_online,
            none=self._handle_none,
        )
        self._executor = QueuedActionExecutor()
        self._email_state = ConversationEmailState()
        self._pending_actions: list[dict[str, Any]] = []
        self._pending_email_confirmation: Optional[str] = None
        self._awaiting_corrected_meeting_email = False
        self._flush_lock = asyncio.Lock()
        self._flushed = False

    async def run(self, history: list[Message], question: str) -> ActionResult:
        deterministic = self._handle_email_control_turn(question)
        if deterministic is not None:
            return deterministic
        if not should_classify_business_action(history, question):
            return ActionResult(response=None, status="no_action")
        state = await self._graph.ainvoke({"history": history, "question": question})
        return ActionResult(response=state.get("response"), status=state.get("action_status"))

    def _handle_email_control_turn(self, question: str) -> Optional[ActionResult]:
        result = self._handle_pending_email_confirmation(question)
        if result is not None:
            return result
        result = self._handle_corrected_meeting_email(question)
        if result is not None:
            return result

        result = self._email_state.handle_control_turn(
            question,
            has_pending_meeting=self._has_pending_action("online_meet"),
        )
        if result and result.email:
            self._queue_action("online_meet", {"email": result.email, "email_verified": False})
        if result:
            return ActionResult(
                response=result.response,
                status=result.status,
            )
        return None

    async def _decide(self, state: ActionState) -> ActionState:
        history = state.get("history", [])
        question = state["question"]
        if fallback_action(history, question) != "none":
            state["decision"] = parse_decision("{}", history, question)
            return state
        transcript = format_transcript(history, question)
        prompt = [
            {"role": "system", "content": ACTION_CLASSIFIER_PROMPT},
            {"role": "user", "content": transcript},
        ]
        raw = await collect_reply(self._provider, prompt)
        state["decision"] = parse_decision(raw, history, question)
        return state

    def _route(self, state: ActionState) -> ActionType:
        return state.get("decision", {}).get("action", "none")

    async def _handle_admin_followup(self, state: ActionState) -> ActionState:
        self._queue_action("admin_followup", state["decision"])
        state["response"] = "Sure, I have noted that you want admin contact details. Our team will follow up with you."
        state["action_status"] = "admin_followup_queued"
        return state

    async def _handle_in_person(self, state: ActionState) -> ActionState:
        decision = state["decision"]
        self._queue_action("in_person_meet", decision)
        state["response"] = (
            "Sure, I have noted that you want an in-person meeting. "
            "Our team will contact you to confirm."
        )
        state["action_status"] = "in_person_queued"
        return state

    async def _handle_online(self, state: ActionState) -> ActionState:
        decision = state["decision"]
        email = self._effective_email(decision)
        if not email:
            state["response"] = "Sure, I can arrange a calendar meeting. What email address should I send the invite to?"
            state["action_status"] = "online_missing_email"
            return state
        self._email_state.remember(email)

        if not self._is_email_verified(email):
            self._pending_email_confirmation = email
            self._queue_action("online_meet", {**decision, "email": email, "email_verified": False})
            state["response"] = f"I heard your email as {email}. Is that correct?"
            state["action_status"] = "online_email_confirmation_required"
            return state

        if not self._has_meeting_time(decision):
            self._queue_action("online_meet", {**decision, "email": email, "email_verified": True})
            state["response"] = "What date and time should I schedule the calendar meeting for?"
            state["action_status"] = "online_missing_time"
            return state

        self._queue_action("online_meet", {**decision, "email": email, "email_verified": True})
        state["response"] = "I have your email. I will schedule the calendar meeting when we wrap up."
        state["action_status"] = "online_queued"
        return state

    async def _handle_none(self, state: ActionState) -> ActionState:
        state["response"] = None
        state["action_status"] = "no_action"
        return state

    def _queue_action(self, action: ActionType, decision: dict) -> None:
        if action == "online_meet":
            existing = self._find_pending_action("online_meet")
            if existing is not None:
                self._merge_online_meeting(existing, decision)
                return

        key = (action, decision.get("email"), decision.get("summary"))
        for item in self._pending_actions:
            if (item["action"], item.get("email"), item.get("summary")) == key:
                return
        self._pending_actions.append({"action": action, "action_id": self._new_action_id(action), **decision})

    def _merge_online_meeting(self, existing: dict[str, Any], decision: dict) -> None:
        """Keep meeting details stable while allowing later email corrections."""
        if decision.get("email"):
            existing["email"] = decision["email"]
        if "email_verified" in decision:
            existing["email_verified"] = decision["email_verified"]

        requested_time = decision.get("requested_time")
        if requested_time:
            existing["requested_time"] = requested_time
            if decision.get("summary"):
                existing["summary"] = decision["summary"]
            return

        if not existing.get("summary") and decision.get("summary"):
            existing["summary"] = decision["summary"]

    def _handle_pending_email_confirmation(self, question: str) -> Optional[ActionResult]:
        if not self._pending_email_confirmation:
            return None
        lower = question.lower()
        if _is_negative_confirmation(lower):
            self._pending_email_confirmation = None
            self._awaiting_corrected_meeting_email = True
            return ActionResult(
                response="No problem. Please tell me the correct email address.",
                status="online_email_rejected",
            )

        replacement = normalize_email(extract_email(question)) or self._email_state.correct_from_text(question)
        if replacement and replacement != self._pending_email_confirmation:
            self._pending_email_confirmation = replacement
            self._email_state.remember(replacement)
            self._queue_action("online_meet", {"email": replacement, "email_verified": False})
            return ActionResult(
                response=f"I heard your email as {replacement}. Is that correct?",
                status="online_email_confirmation_required",
            )

        if _is_positive_confirmation(lower):
            email = self._pending_email_confirmation
            self._pending_email_confirmation = None
            self._awaiting_corrected_meeting_email = False
            self._email_state.remember(email)
            self._queue_action("online_meet", {"email": email, "email_verified": True})
            if not self._has_meeting_time({}):
                return ActionResult(
                    response="Thanks, I have verified your email. What date and time should I schedule the meeting for?",
                    status="online_missing_time",
                )
            return ActionResult(
                response="Thanks, I have verified your email. I will schedule the calendar meeting when we wrap up.",
                status="online_email_verified",
            )
        return None

    def _handle_corrected_meeting_email(self, question: str) -> Optional[ActionResult]:
        if not self._awaiting_corrected_meeting_email:
            return None
        email = normalize_email(extract_email(question)) or self._email_state.correct_from_text(question)
        if not email:
            return ActionResult(
                response="Please share the full correct email address for the calendar invite.",
                status="online_missing_corrected_email",
            )
        self._awaiting_corrected_meeting_email = False
        self._pending_email_confirmation = email
        self._email_state.remember(email)
        self._queue_action("online_meet", {"email": email, "email_verified": False})
        return ActionResult(
            response=f"I heard your email as {email}. Is that correct?",
            status="online_email_confirmation_required",
        )

    def _effective_email(self, decision: dict[str, Any]) -> Optional[str]:
        return decision.get("email") or self._email_state.current_email or self._pending_action_value("online_meet", "email")

    def _is_email_verified(self, email: str) -> bool:
        existing = self._find_pending_action("online_meet")
        return bool(existing and existing.get("email") == email and existing.get("email_verified"))

    def _has_meeting_time(self, decision: dict[str, Any]) -> bool:
        existing_summary = self._pending_action_value("online_meet", "summary")
        existing_time = self._pending_action_value("online_meet", "requested_time")
        value = decision.get("requested_time") or decision.get("summary") or existing_time or existing_summary
        return bool(value and _has_time_signal(str(value)))

    def _pending_action_value(self, action: ActionType, key: str) -> Any:
        existing = self._find_pending_action(action)
        return existing.get(key) if existing else None

    @staticmethod
    def _new_action_id(action: ActionType) -> str:
        return f"{action}-{uuid.uuid4().hex}"

    def _find_pending_action(self, action: ActionType) -> Optional[dict[str, Any]]:
        return next((item for item in self._pending_actions if item["action"] == action), None)

    def _has_pending_action(self, action: ActionType) -> bool:
        return self._find_pending_action(action) is not None

    async def flush_pending_actions(self, history: list[Message]) -> None:
        async with self._flush_lock:
            if self._flushed:
                return
            self._flushed = True
            await self._executor.flush(self._pending_actions, history)
            self._pending_actions = []


def _is_positive_confirmation(lower: str) -> bool:
    return any(
        phrase in lower
        for phrase in (
            "yes",
            "yeah",
            "yep",
            "correct",
            "right",
            "that's correct",
            "that is correct",
            "looks good",
            "go ahead",
        )
    )


def _is_negative_confirmation(lower: str) -> bool:
    return any(
        phrase in lower
        for phrase in (
            "no",
            "wrong",
            "incorrect",
            "not correct",
            "not right",
            "not writing",
            "mistake",
        )
    )


def _has_time_signal(value: str) -> bool:
    lower = value.lower()
    return any(
        token in lower
        for token in (
            "today",
            "tomorrow",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
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
            "noon",
            "morning",
            "evening",
            "am",
            "pm",
            "/",
            "-",
        )
    )
