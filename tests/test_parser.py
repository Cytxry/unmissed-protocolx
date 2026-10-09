import unittest

from app import UserError, parse_transcript, parse_transcript_with_warnings


class TranscriptParserTests(unittest.TestCase):
    def parse_one(self, text):
        messages, warnings = parse_transcript_with_warnings(text)
        self.assertEqual(warnings, [])
        self.assertEqual(len(messages), 1)
        return messages[0]

    def test_name_colon_message_without_timestamp(self):
        message = self.parse_one("Maya: Send the notes.")
        self.assertEqual(message, {
            "id": "m1", "timestamp": "", "sender": "Maya", "text": "Send the notes."
        })

    def test_bracket_timestamp(self):
        message = self.parse_one("[10:15] Dev: Ready?")
        self.assertEqual((message["timestamp"], message["sender"], message["text"]),
                         ("10:15", "Dev", "Ready?"))

    def test_bracketed_export_timestamp_seconds_and_phone_sender(self):
        message = self.parse_one("[10/9/26, 10:48:04 AM] +91 63662 36404: We are in the class room")
        self.assertEqual((message["timestamp"], message["sender"], message["text"]),
                         ("10/9/26, 10:48:04 AM", "+91 63662 36404", "We are in the class room"))

    def test_iso_timestamp(self):
        message = self.parse_one("2026-10-09 14:30 - Maya: Call me.")
        self.assertEqual((message["timestamp"], message["sender"], message["text"]),
                         ("2026-10-09 14:30", "Maya", "Call me."))

    def test_common_export_timestamp_shape(self):
        # Tests the timestamp/header syntax only; this is not a claim of platform export compatibility.
        message = self.parse_one("9/10/26, 2:30 PM - Maya: Hi there")
        self.assertEqual((message["timestamp"], message["sender"], message["text"]),
                         ("9/10/26, 2:30 PM", "Maya", "Hi there"))

    def test_unicode_sender_and_message(self):
        message = self.parse_one("李雷 🧑🏽‍💻: 你好，团队！")
        self.assertEqual((message["sender"], message["text"]), ("李雷 🧑🏽‍💻", "你好，团队！"))

    def test_multiline_body_is_preserved(self):
        message = self.parse_one("Maya: first line\n  second line\n\tthird line")
        self.assertEqual(message["text"], "first line\n  second line\n\tthird line")

    def test_urls_and_colons_in_message_text_are_preserved(self):
        message = self.parse_one("Maya: Notes: https://example.test/path?a=1:2")
        self.assertEqual(message["sender"], "Maya")
        self.assertEqual(message["text"], "Notes: https://example.test/path?a=1:2")

    def test_media_placeholder_is_preserved(self):
        message = self.parse_one("Maya: <Media omitted>")
        self.assertEqual(message["text"], "<Media omitted>")

    def test_deleted_message_notice_is_preserved_as_original_message_text(self):
        message = self.parse_one("Maya: This message was deleted")
        self.assertEqual(message["text"], "This message was deleted")

    def test_duplicate_messages_are_not_silently_deduplicated(self):
        messages, warnings = parse_transcript_with_warnings("Maya: Same text\nMaya: Same text")
        self.assertEqual(warnings, [])
        self.assertEqual([message["id"] for message in messages], ["m1", "m2"])
        self.assertEqual([message["text"] for message in messages], ["Same text", "Same text"])

    def test_timestamped_system_notification(self):
        messages, warnings = parse_transcript_with_warnings(
            "9/10/26, 2:30 PM - Messages and calls are end-to-end encrypted."
        )
        self.assertEqual(warnings, [])
        self.assertEqual(messages[0]["sender"], "System")
        self.assertEqual(messages[0]["text"], "Messages and calls are end-to-end encrypted.")
        self.assertEqual(messages[0]["timestamp"], "9/10/26, 2:30 PM")

    def test_actor_system_notification(self):
        message = self.parse_one("[10:15] 李雷 added Maya to the group")
        self.assertEqual((message["sender"], message["text"]), ("李雷", "李雷 added Maya to the group"))

    def test_un_timestamped_system_notice(self):
        message = self.parse_one(
            "Messages and calls are end-to-end encrypted. Only people in this chat can read them."
        )
        self.assertEqual((message["sender"], message["text"]),
                         ("System", "Messages and calls are end-to-end encrypted. Only people in this chat can read them."))

    def test_unparsed_lines_are_preserved_and_warned(self):
        messages, warnings = parse_transcript_with_warnings(
            "intro without a header\nMaya: hello\nunlabelled continuation"
        )
        self.assertEqual([m["id"] for m in messages], ["m1", "m2"])
        self.assertEqual(messages[0]["sender"], "Unknown")
        self.assertEqual(messages[0]["text"], "intro without a header")
        self.assertEqual(messages[1]["text"], "hello\nunlabelled continuation")
        self.assertEqual(len(warnings), 1)
        self.assertIn("line 1, 3", warnings[0])

    def test_source_ids_follow_original_message_order(self):
        messages = parse_transcript("A: first\nB: second\nA: third")
        self.assertEqual([m["id"] for m in messages], ["m1", "m2", "m3"])
        self.assertEqual([m["sender"] for m in messages], ["A", "B", "A"])

    def test_empty_input_still_has_a_helpful_error(self):
        with self.assertRaisesRegex(UserError, "transcript is empty"):
            parse_transcript(" \n\t")


if __name__ == "__main__":
    unittest.main()
