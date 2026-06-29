from __future__ import annotations

from typing import Any

from app.agent.actions.llm_utils import collect_reply
from app.agent.actions.messages import admin_final_body, material_email_body
from app.agent.actions.parsing import format_transcript
from app.agent.actions.prompts import ADMIN_SUMMARY_PROMPT
from app.config import settings
from app.core.logging import get_logger
from app.llm.base import Message
from app.llm.factory import get_llm_provider
from app.tools.calendar import schedule_online_meeting
from app.tools.email import send_email
from app.tools.notify import send_push

log = get_logger(__name__)


class QueuedActionExecutor:
    async def flush(self, actions: list[dict[str, Any]], history: list[Message]) -> None:
        if not history:
            return

        summary = await summarize_for_admin(history)
        action_lines: list[str] = []

        for action in actions:
            kind = action["action"]
            try:
                if kind == "send_material":
                    action_lines.append(await self._send_material(action))
                elif kind == "online_meet":
                    action_lines.append(await self._schedule_online(action))
                elif kind == "in_person_meet":
                    action_lines.append(f"In-person meeting requested: {action.get('summary')}")
            except Exception as exc:
                log.warning("business action failed (%s): %s", kind, exc)
                action_lines.append(f"{kind} failed: {exc}")

        admin_body = admin_final_body(summary, action_lines)
        push_title = "Voice Agent: Action + summary" if action_lines else "Voice Agent: Call summary"
        await send_push(admin_body, title=push_title)
        if settings.admin_email:
            await send_email(settings.admin_email, "Voice Agent call summary", admin_body)

    async def _send_material(self, action: dict[str, Any]) -> str:
        email = action.get("email")
        if not email:
            return f"Material/contact request needs email: {action.get('summary')}"
        sent = await send_email(email, "Real estate and renovation details", material_email_body())
        status = "sent" if sent else "failed"
        return f"Material/contact email {status} for {email}: {action.get('summary')}"

    async def _schedule_online(self, action: dict[str, Any]) -> str:
        email = action.get("email")
        if not email:
            return f"Online meeting request needs email: {action.get('summary')}"
        result = await schedule_online_meeting(
            attendee_email=email,
            requested_time=action.get("requested_time") or action.get("summary"),
            summary="Online real estate consultation scheduled by VoiceAgent.",
            request_id=action.get("action_id"),
        )
        detail = result.message
        if result.event_link:
            detail += f" Link: {result.event_link}"
        return f"Online meeting for {email}: {detail}. Request: {action.get('summary')}"


async def summarize_for_admin(history: list[Message]) -> str:
    provider = get_llm_provider()
    messages = [
        {"role": "system", "content": ADMIN_SUMMARY_PROMPT},
        {"role": "user", "content": format_transcript(history, "")},
    ]
    return (await collect_reply(provider, messages)).strip()
