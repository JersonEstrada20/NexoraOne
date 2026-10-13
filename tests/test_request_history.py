import unittest

from nexora.request_history import append_request_event, latest_request_message, parse_request_history


class RequestHistoryTests(unittest.TestCase):
    def test_events_keep_message_author_kind_and_timestamp(self):
        history = append_request_event(
            "", "We found the result\nSecond line", author_id=42,
            kind="reply", created_at="2026-10-13T12:00:00Z",
        )
        events = parse_request_history(
            history, request_text="/lookup value", request_created_at="2026-10-13T11:00:00Z",
            user_id=7, username="client",
        )
        self.assertEqual(2, len(events))
        self.assertEqual(("request", "@client", "/lookup value"),
                         (events[0]["kind"], events[0]["author_label"], events[0]["text"]))
        self.assertEqual(("reply", "Admin 42", "2026-10-13T12:00:00Z"),
                         (events[1]["kind"], events[1]["author_label"], events[1]["at"]))
        self.assertEqual("We found the result\nSecond line", latest_request_message(history))

    def test_legacy_timestamped_notes_remain_readable(self):
        events = parse_request_history("[2026-10-12T10:00:00Z] legacy note", resolved_by=5)
        self.assertEqual("legacy note", events[0]["text"])
        self.assertEqual("Admin 5", events[0]["author_label"])

    def test_empty_note_does_not_append_an_event(self):
        self.assertEqual("previous", append_request_event("previous", "  "))


if __name__ == "__main__":
    unittest.main()
