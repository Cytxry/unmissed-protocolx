import unittest
from types import SimpleNamespace
from unittest.mock import patch

import app
from product_logic import redact_phone_numbers


class PrivacyTests(unittest.TestCase):
    def test_generated_analysis_is_masked_but_source_message_stays_verbatim(self):
        source = {"id": "m1", "timestamp": "2026-10-09 14:30", "sender": "Maya",
                  "text": "Maya should call +1 (415) 555-0137 about the launch."}
        model_result = {
            "summary": "Maya should call +1 (415) 555-0137.",
            "findings": [{
                "category": "action", "title": "Maya to call +1 (415) 555-0137",
                "detail": "Maya should call +1 (415) 555-0137 about the launch.",
                "owner": "Maya", "due": "", "when": "", "confidence": "high",
                "evidence": ["m1"], "conflictEvidence": [],
            }],
        }
        with patch("app.ollama_json", return_value=model_result):
            result = app.analyze_dashboard_chunk("test-model", [source], "Maya")

        self.assertEqual(source["text"], "Maya should call +1 (415) 555-0137 about the launch.")
        self.assertNotIn("Maya", result["summary"])
        self.assertNotIn("415", result["summary"])
        finding = result["findings"][0]
        self.assertEqual(finding["owner"], "You")
        self.assertNotIn("Maya", finding["title"] + finding["detail"])
        self.assertNotIn("415", finding["title"] + finding["detail"])
        self.assertEqual(finding["evidence"], ["m1"])

    def test_remote_ollama_url_is_rejected_before_request(self):
        with patch.object(app, "OLLAMA_URL", "https://example.com:11434"), patch("app.build_opener") as build_opener:
            with self.assertRaisesRegex(app.UserError, "Conversation data was not sent"):
                app.ollama_json("qwen2.5:3b", "system", "conversation content")
        build_opener.assert_not_called()

    def test_loopback_ollama_urls_are_allowed(self):
        app.validate_local_ollama_url("http://127.0.0.1:11434")
        app.validate_local_ollama_url("http://localhost:11434")
        app.validate_local_ollama_url("http://[::1]:11434")

    def test_supplied_identity_is_omitted_from_public_job_metadata(self):
        public = app.public_job_data({"state": "done", "_userName": "Maya", "summary": "You were mentioned."})
        self.assertEqual(public, {"state": "done", "summary": "You were mentioned."})

    def test_identity_is_only_sent_for_mention_or_assignment_questions(self):
        self.assertTrue(app.question_needs_user_identity("Did anyone mention me?"))
        self.assertTrue(app.question_needs_user_identity("What do I need to do next?"))
        self.assertFalse(app.question_needs_user_identity("What decisions were made?"))

    def test_http_diagnostic_log_masks_phone_numbers(self):
        handler = SimpleNamespace(log_date_time_string=lambda: "now")
        with patch("builtins.print") as logged:
            app.Handler.log_message(handler, "%s", "request to /api/jobs/1234567890")
        message = logged.call_args.args[0]
        self.assertIn("[phone number]", message)
        self.assertNotIn("1234567890", message)

    def test_phone_redaction_leaves_date_time_and_source_ids_intact(self):
        text = "m4 at 2026-10-09 14:30 called 415-555-0137"
        safe = redact_phone_numbers(text)
        self.assertEqual(safe, "m4 at 2026-10-09 14:30 called [phone number]")


if __name__ == "__main__":
    unittest.main()
