from __future__ import annotations

import unittest

from app.agent.actions.executor import QueuedActionExecutor
from app.agent.actions.email_state import ConversationEmailState
from app.agent.actions.parsing import fallback_action
from app.agent.business_actions import BusinessActionAgent
from app.tools.calendar import _parse_or_default_time


class ActionSchedulingTests(unittest.TestCase):
    def test_online_meeting_keeps_requested_time_when_email_is_corrected(self) -> None:
        existing = {
            "action": "online_meet",
            "action_id": "online_meet-test",
            "email": "wrong@example.com",
            "requested_time": "2026-07-01T12:00:00+05:30",
            "summary": "Schedule a calendar meet on Wednesday 07/01/2026 at twelve noon.",
        }

        BusinessActionAgent._merge_online_meeting(
            object.__new__(BusinessActionAgent),
            existing,
            {
                "email": "sspandere26@gmail.com",
                "summary": "Thanks, I have updated the meeting email.",
            },
        )

        self.assertEqual(existing["email"], "sspandere26@gmail.com")
        self.assertEqual(existing["requested_time"], "2026-07-01T12:00:00+05:30")
        self.assertEqual(
            existing["summary"],
            "Schedule a calendar meet on Wednesday 07/01/2026 at twelve noon.",
        )

    def test_no_red_email_correction_removes_red_from_domain(self) -> None:
        state = ConversationEmailState()
        state.remember("sspandere26@redgmail.com")

        result = state.handle_control_turn("No. There is no red of the ad.", has_pending_meeting=True)

        self.assertIsNotNone(result)
        self.assertEqual(result.email, "sspandere26@gmail.com")

    def test_lowercase_email_correction(self) -> None:
        state = ConversationEmailState()
        state.remember("ssPandERe26@gmail.com")

        result = state.handle_control_turn("All letters in the email are smaller case.", has_pending_meeting=True)

        self.assertIsNotNone(result)
        self.assertEqual(result.email, "sspandere26@gmail.com")

    def test_natural_calendar_time_parses_july_first_noon(self) -> None:
        parsed = _parse_or_default_time("Wednesday 07/01/2026 at twelve noon")

        self.assertEqual(parsed.year, 2026)
        self.assertEqual(parsed.month, 7)
        self.assertEqual(parsed.day, 1)
        self.assertEqual(parsed.hour, 12)
        self.assertEqual(parsed.minute, 0)

    def test_admin_contact_request_does_not_route_to_calendar(self) -> None:
        self.assertEqual(fallback_action([], "Please provide admin contact details."), "admin_followup")

    def test_meeting_time_reply_continues_existing_calendar_flow(self) -> None:
        history = [{"role": "assistant", "content": "What date and time should I schedule the meeting for?"}]

        self.assertEqual(fallback_action(history, "Wednesday at twelve noon"), "online_meet")


class EmailVerificationFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_email_keeps_agent_waiting_for_corrected_email(self) -> None:
        agent = _agent_with_pending_meeting(email="26@gmail.com", summary="Schedule a meeting with admin.")

        rejected = agent._handle_pending_email_confirmation("This is not writing me.")
        corrected = agent._handle_email_control_turn("Sspandere26@gmail.com.")

        self.assertEqual(rejected.status, "online_email_rejected")
        self.assertEqual(corrected.status, "online_email_confirmation_required")
        self.assertIn("sspandere26@gmail.com", corrected.response)

    async def test_verified_email_without_time_asks_for_meeting_time(self) -> None:
        agent = _agent_with_pending_meeting(email="sspandere26@gmail.com", summary="Schedule a meeting with admin.")

        result = agent._handle_pending_email_confirmation("yes correct")

        self.assertIsNotNone(result)
        self.assertEqual(result.status, "online_missing_time")
        self.assertIn("date and time", result.response)

    async def test_executor_does_not_schedule_unverified_email(self) -> None:
        executor = QueuedActionExecutor()

        result = await executor._schedule_online(
            {
                "action": "online_meet",
                "email": "user@example.com",
                "email_verified": False,
                "summary": "Schedule a calendar meet on Wednesday 07/01/2026 at twelve noon.",
            }
        )

        self.assertIn("verified email", result)


def _agent_with_pending_meeting(*, email: str, summary: str) -> BusinessActionAgent:
    agent = object.__new__(BusinessActionAgent)
    agent._email_state = ConversationEmailState()
    agent._email_state.remember(email)
    agent._pending_email_confirmation = email
    agent._awaiting_corrected_meeting_email = False
    agent._pending_actions = [
        {
            "action": "online_meet",
            "action_id": "online_meet-test",
            "email": email,
            "email_verified": False,
            "summary": summary,
        }
    ]
    return agent


if __name__ == "__main__":
    unittest.main()
