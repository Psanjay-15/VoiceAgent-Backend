from __future__ import annotations

import unittest

from app.agent.actions.email_state import ConversationEmailState
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

    def test_natural_calendar_time_parses_july_first_noon(self) -> None:
        parsed = _parse_or_default_time("Wednesday 07/01/2026 at twelve noon")

        self.assertEqual(parsed.year, 2026)
        self.assertEqual(parsed.month, 7)
        self.assertEqual(parsed.day, 1)
        self.assertEqual(parsed.hour, 12)
        self.assertEqual(parsed.minute, 0)


if __name__ == "__main__":
    unittest.main()
