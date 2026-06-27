from __future__ import annotations

from typing import Any, Optional

from langgraph.graph import END, StateGraph

from app.agent.actions.messages import admin_action_body, admin_final_body, material_email_body
from app.agent.actions.models import ActionResult, ActionState, ActionType
from app.agent.actions.parsing import format_transcript, parse_decision
from app.config import settings
from app.core.logging import get_logger
from app.llm.base import Message
from app.llm.factory import get_llm_provider
from app.tools.calendar import schedule_online_meeting
from app.tools.email import send_email
from app.tools.notify import send_push

log = get_logger(__name__)


class BusinessActionAgent:
    """LangGraph router for business actions around the voice conversation."""

    def __init__(self) -> None:
        self._provider = get_llm_provider()
        self._graph = self._build_graph()
        self._in_person_notified = False
        self._material_emails: set[str] = set()
        self._online_meeting_emails: set[str] = set()
        self._pending_actions: list[dict[str, Any]] = []
        self._current_email: Optional[str] = None

    async def run(self, history: list[Message], question: str) -> ActionResult:
        deterministic = self._handle_email_control_turn(question)
        if deterministic is not None:
            return deterministic
        state = await self._graph.ainvoke({"history": history, "question": question})
        return ActionResult(response=state.get("response"), status=state.get("action_status"))

    def _handle_email_control_turn(self, question: str) -> Optional[ActionResult]:
        if self._asks_to_confirm_email(question):
            response = (
                f"I have {self._current_email} as the email address."
                if self._current_email
                else "I do not have an email address yet. Could you share it?"
            )
            return ActionResult(response=response, status="email_confirmed")

        corrected = self._correct_email_from_text(question)
        if corrected and self._has_pending_action("online_meet"):
            self._current_email = corrected
            self._queue_action("online_meet", {"email": corrected})
            return ActionResult(
                response=f"Thanks, I have updated the meeting email to {corrected}.",
                status="online_email_updated",
            )
        return None

    def _build_graph(self):
        graph = StateGraph(ActionState)
        graph.add_node("decide", self._decide)
        graph.add_node("in_person", self._handle_in_person)
        graph.add_node("online", self._handle_online)
        graph.add_node("material", self._handle_material)
        graph.add_node("none", self._handle_none)
        graph.set_entry_point("decide")
        graph.add_conditional_edges(
            "decide",
            self._route,
            {
                "in_person_meet": "in_person",
                "online_meet": "online",
                "send_material": "material",
                "none": "none",
            },
        )
        graph.add_edge("in_person", END)
        graph.add_edge("online", END)
        graph.add_edge("material", END)
        graph.add_edge("none", END)
        return graph.compile()

    async def _decide(self, state: ActionState) -> ActionState:
        history = state.get("history", [])
        question = state["question"]
        transcript = format_transcript(history, question)
        prompt = [
            {
                "role": "system",
                "content": (
                    "You classify real estate voice-agent turns and extract tool fields. "
                    "Return only JSON with these keys: action, email, requested_time, "
                    "material_type, summary. action must be one of in_person_meet, "
                    "online_meet, send_material, none. Decide mainly from the LATEST "
                    "Caller line. Use earlier transcript only to fill missing fields "
                    "like email, location, budget, and time. Return none for normal "
                    "qualification details like budget, BHK, possession timeline, area, "
                    "or corrections unless the latest caller line explicitly asks for a "
                    "meeting, contact details, brochure, or provides an email after you "
                    "asked for one. Use online_meet when the caller asks to schedule "
                    "a meeting, calendar invite, admin meeting, online/video/Google "
                    "Meet meeting, or appointment unless they clearly ask for a "
                    "physical site or office visit. Use in_person_meet for site visits, "
                    "office visits, property visits, or any physical meeting request. "
                    "Use send_material when the caller asks for contact details, "
                    "brochure, catalogue, pricing sheet, or details by email. "
                    "requested_time should be ISO-8601 if clear, otherwise null. "
                    "summary must be a concise admin summary."
                ),
            },
            {"role": "user", "content": transcript},
        ]
        raw = await _collect_reply(self._provider, prompt)
        decision = parse_decision(raw, history, question)
        state["decision"] = decision
        return state

    def _route(self, state: ActionState) -> ActionType:
        return state.get("decision", {}).get("action", "none")

    async def _handle_in_person(self, state: ActionState) -> ActionState:
        decision = state["decision"]
        already_notified = self._in_person_notified
        self._in_person_notified = True
        self._queue_action("in_person_meet", decision)
        state["action_status"] = "in_person_queued"
        if already_notified:
            state["response"] = "Got it, I have noted those meeting preferences. Our team will contact you to confirm."
        else:
            state["response"] = (
                "Sure, I have noted that you want an in-person meeting. "
                "Could you also share your preferred area and time if you have one?"
            )
        return state

    async def _handle_online(self, state: ActionState) -> ActionState:
        decision = state["decision"]
        email = decision.get("email")
        if not email:
            state["action_status"] = "online_missing_email"
            state["response"] = "Sure, I can arrange a calendar meeting. What email address should I send the invite to?"
            return state
        self._current_email = email
        if email in self._online_meeting_emails:
            state["action_status"] = "online_already_queued"
            state["response"] = "I already have your email for the calendar meeting. I will include it in the final request."
            return state

        self._queue_action("online_meet", decision)
        state["action_status"] = "online_queued"
        self._online_meeting_emails.add(email)
        state["response"] = "I have your email. I will schedule the calendar meeting when we wrap up."
        return state

    async def _handle_material(self, state: ActionState) -> ActionState:
        decision = state["decision"]
        email = decision.get("email")
        if not email:
            state["action_status"] = "material_missing_email"
            state["response"] = "Sure, I can send that to you. What email address should I use?"
            return state
        self._current_email = email
        if email in self._material_emails:
            state["action_status"] = "material_already_handled"
            state["response"] = "I already have your email and have noted the request. I will send the details there when we wrap up."
            return state

        self._queue_action("send_material", decision)
        state["action_status"] = "material_queued"
        self._material_emails.add(email)
        state["response"] = "I have noted your email. I will send the contact details when we wrap up."
        return state

    async def _handle_none(self, state: ActionState) -> ActionState:
        question = state.get("question", "")
        if self._asks_to_confirm_email(question):
            state["response"] = (
                f"I have {self._current_email} as the email address."
                if self._current_email
                else "I do not have an email address yet. Could you share it?"
            )
            state["action_status"] = "email_confirmed"
            return state

        decision = state.get("decision", {})
        email = decision.get("email")
        corrected = self._correct_email_from_text(question)
        if corrected and self._has_pending_action("online_meet"):
            self._current_email = corrected
            self._queue_action("online_meet", {**decision, "email": corrected})
            state["response"] = f"Thanks, I have updated the meeting email to {corrected}."
            state["action_status"] = "online_email_updated"
            return state

        if email and email != self._current_email and self._has_pending_action("online_meet"):
            self._current_email = email
            self._queue_action("online_meet", decision)
            state["response"] = f"Thanks, I have updated the meeting email to {email}."
            state["action_status"] = "online_email_updated"
            return state
        state["response"] = None
        state["action_status"] = "no_action"
        return state

    @staticmethod
    def _asks_to_confirm_email(text: str) -> bool:
        lower = text.lower()
        return "email" in lower and any(phrase in lower for phrase in ("show", "repeat", "confirm", "what is", "tell me"))

    def _correct_email_from_text(self, text: str) -> Optional[str]:
        if not self._current_email:
            return None
        lower = text.lower()
        if "email" not in lower:
            return None
        if "no dot" in lower or "without dot" in lower or "there is no dot" in lower:
            local, sep, domain = self._current_email.partition("@")
            if sep:
                return f"{local.replace('.', '')}@{domain}"
        return None

    def _queue_action(self, action: ActionType, decision: dict) -> None:
        if action == "online_meet":
            existing = self._find_pending_action("online_meet")
            if existing is not None:
                for key in ("email", "requested_time", "summary", "material_type"):
                    if decision.get(key):
                        existing[key] = decision[key]
                if decision.get("email"):
                    self._online_meeting_emails.add(decision["email"])
                return

        key = (action, decision.get("email"), decision.get("summary"))
        for item in self._pending_actions:
            if (item["action"], item.get("email"), item.get("summary")) == key:
                return
        self._pending_actions.append({"action": action, **decision})

    def _find_pending_action(self, action: ActionType) -> Optional[dict[str, Any]]:
        return next((item for item in self._pending_actions if item["action"] == action), None)

    def _has_pending_action(self, action: ActionType) -> bool:
        return self._find_pending_action(action) is not None

    async def flush_pending_actions(self, history: list[Message]) -> None:
        if not history:
            return

        summary = await summarize_for_admin(history)
        action_lines = []
        should_push_action_notice = False

        for action in self._pending_actions:
            kind = action["action"]
            try:
                if kind == "send_material":
                    result = await self._send_material_at_end(action)
                    action_lines.append(result)
                    should_push_action_notice = True
                elif kind == "online_meet":
                    result = await self._schedule_online_at_end(action)
                    action_lines.append(result)
                    should_push_action_notice = True
                elif kind == "in_person_meet":
                    action_lines.append(f"In-person meeting requested: {action.get('summary')}")
                    should_push_action_notice = True
            except Exception as e:
                log.warning("business action failed (%s): %s", kind, e)
                action_lines.append(f"{kind} failed: {e}")
                should_push_action_notice = True

        admin_body = admin_final_body(summary, action_lines)
        await send_push(admin_body, title="Voice Agent: Call summary")
        if should_push_action_notice:
            await send_push(admin_action_body(action_lines), title="Voice Agent: Action needed")
        if settings.admin_email:
            await send_email(settings.admin_email, "Voice Agent call summary", admin_body)

        self._pending_actions = []

    async def _send_material_at_end(self, action: dict) -> str:
        email = action.get("email")
        if not email:
            return f"Material/contact request needs email: {action.get('summary')}"
        sent = await send_email(email, "Real estate and renovation details", material_email_body())
        status = "sent" if sent else "failed"
        return f"Material/contact email {status} for {email}: {action.get('summary')}"

    async def _schedule_online_at_end(self, action: dict) -> str:
        email = action.get("email")
        if not email:
            return f"Online meeting request needs email: {action.get('summary')}"
        result = await schedule_online_meeting(
            attendee_email=email,
            requested_time=action.get("requested_time") or action.get("summary"),
            summary="Online real estate consultation scheduled by VoiceAgent.",
        )
        detail = result.message
        if result.event_link:
            detail += f" Link: {result.event_link}"
        return f"Online meeting for {email}: {detail}. Request: {action.get('summary')}"


async def summarize_for_admin(history: list[Message]) -> str:
    provider = get_llm_provider()
    messages = [
        {
            "role": "system",
            "content": (
                "Summarize this real estate voice-agent conversation for an admin. "
                "Include intent, location, budget, timeline, meeting/email requests, "
                "missing details, and next action. Keep it concise."
            ),
        },
        {"role": "user", "content": format_transcript(history, "")},
    ]
    summary = await _collect_reply(provider, messages)
    return summary.strip()


async def _collect_reply(provider, messages: list[Message]) -> str:
    chunks = []
    async for token in provider.stream_reply(messages):
        chunks.append(token)
    return "".join(chunks)
