from __future__ import annotations

import asyncio
import uuid
from typing import Any, Optional

from app.agent.actions.email_state import ConversationEmailState
from app.agent.actions.executor import QueuedActionExecutor
from app.agent.actions.graph import build_business_action_graph
from app.agent.actions.llm_utils import collect_reply
from app.agent.actions.models import ActionResult, ActionState, ActionType
from app.agent.actions.parsing import fallback_action, format_transcript, parse_decision, should_classify_business_action
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
            in_person=self._handle_in_person,
            online=self._handle_online,
            none=self._handle_none,
        )
        self._executor = QueuedActionExecutor()
        self._email_state = ConversationEmailState()
        self._in_person_notified = False
        self._online_meeting_emails: set[str] = set()
        self._pending_actions: list[dict[str, Any]] = []
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
        result = self._email_state.handle_control_turn(
            question,
            has_pending_meeting=self._has_pending_action("online_meet"),
        )
        if result and result.email:
            self._queue_action("online_meet", {"email": result.email})
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

    async def _handle_in_person(self, state: ActionState) -> ActionState:
        decision = state["decision"]
        already_notified = self._in_person_notified
        self._in_person_notified = True
        self._queue_action("in_person_meet", decision)
        if already_notified:
            state["response"] = "Got it, I have noted those meeting preferences. Our team will contact you to confirm."
        else:
            state["response"] = (
                "Sure, I have noted that you want an in-person meeting. "
                "Could you also share your preferred area and time if you have one?"
            )
        state["action_status"] = "in_person_queued"
        return state

    async def _handle_online(self, state: ActionState) -> ActionState:
        decision = state["decision"]
        email = decision.get("email")
        if not email:
            state["response"] = "Sure, I can arrange a calendar meeting. What email address should I send the invite to?"
            state["action_status"] = "online_missing_email"
            return state
        self._email_state.remember(email)
        if email in self._online_meeting_emails:
            state["response"] = "I already have your email for the calendar meeting. I will include it in the final request."
            state["action_status"] = "online_already_queued"
            return state

        self._queue_action("online_meet", decision)
        self._online_meeting_emails.add(email)
        state["response"] = "I have your email. I will schedule the calendar meeting when we wrap up."
        state["action_status"] = "online_queued"
        return state

    async def _handle_none(self, state: ActionState) -> ActionState:
        decision = state.get("decision", {})
        email = decision.get("email")
        if email and email != self._email_state.current_email and self._has_pending_action("online_meet"):
            self._email_state.remember(email)
            self._queue_action("online_meet", decision)
            state["response"] = f"Thanks, I have updated the meeting email to {email}."
            state["action_status"] = "online_email_updated"
            return state
        state["response"] = None
        state["action_status"] = "no_action"
        return state

    def _queue_action(self, action: ActionType, decision: dict) -> None:
        if action == "online_meet":
            existing = self._find_pending_action("online_meet")
            if existing is not None:
                self._merge_online_meeting(existing, decision)
                if decision.get("email"):
                    self._online_meeting_emails.add(decision["email"])
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

        requested_time = decision.get("requested_time")
        if requested_time:
            existing["requested_time"] = requested_time
            if decision.get("summary"):
                existing["summary"] = decision["summary"]
            return

        if not existing.get("summary") and decision.get("summary"):
            existing["summary"] = decision["summary"]

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
