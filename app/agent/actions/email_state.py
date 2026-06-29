from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class EmailControlResult:
    email: Optional[str]
    response: str
    status: str


class ConversationEmailState:
    def __init__(self) -> None:
        self.current_email: Optional[str] = None

    def remember(self, email: str | None) -> None:
        if email:
            self.current_email = email

    def handle_control_turn(self, text: str, *, has_pending_meeting: bool) -> Optional[EmailControlResult]:
        if self._asks_to_confirm_email(text):
            response = (
                f"I have {self.current_email} as the email address."
                if self.current_email
                else "I do not have an email address yet. Could you share it?"
            )
            return EmailControlResult(email=self.current_email, response=response, status="email_confirmed")

        corrected = self._correct_from_text(text)
        if corrected and has_pending_meeting:
            self.current_email = corrected
            return EmailControlResult(
                email=corrected,
                response=f"Thanks, I have updated the meeting email to {corrected}.",
                status="online_email_updated",
            )
        return None

    @staticmethod
    def _asks_to_confirm_email(text: str) -> bool:
        lower = text.lower()
        return "email" in lower and any(phrase in lower for phrase in ("show", "repeat", "confirm", "what is", "tell me"))

    def _correct_from_text(self, text: str) -> Optional[str]:
        if not self.current_email:
            return None
        lower = text.lower()
        if "no dot" in lower or "without dot" in lower or "there is no dot" in lower:
            local, sep, domain = self.current_email.partition("@")
            if sep:
                return f"{local.replace('.', '')}@{domain}"
        if any(phrase in lower for phrase in ("no red", "without red", "there is no red")):
            local, sep, domain = self.current_email.partition("@")
            if sep:
                return f"{local}@{domain.replace('red', '', 1)}"
        return None
