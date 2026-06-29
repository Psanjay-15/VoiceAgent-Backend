from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional, TypedDict

from app.llm.base import Message

ActionType = Literal["admin_followup", "in_person_meet", "online_meet", "none"]


class ActionState(TypedDict, total=False):
    history: list[Message]
    question: str
    decision: dict[str, Any]
    response: Optional[str]
    action_status: Optional[str]


@dataclass
class ActionResult:
    response: Optional[str] = None
    status: Optional[str] = None
