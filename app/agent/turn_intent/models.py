from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TurnIntent = Literal["continue_conversation", "end_conversation"]


@dataclass
class TurnIntentResult:
    intent: TurnIntent
    confidence: float
    reason: str = ""

    @property
    def should_end(self) -> bool:
        return self.intent == "end_conversation" and self.confidence >= 0.75
