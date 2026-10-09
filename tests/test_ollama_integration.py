import os
import unittest

from app import analyze_dashboard_chunk, answer_question_chunk


@unittest.skipUnless(os.environ.get("UNMISSED_RUN_OLLAMA_TESTS") == "1",
                     "set UNMISSED_RUN_OLLAMA_TESTS=1 to call the configured local Ollama model")
class LocalOllamaIntegrationTests(unittest.TestCase):
    def test_real_local_analysis_and_grounded_question(self):
        messages = [
            {"id": "m1", "timestamp": "2026-10-09 10:15", "sender": "Maya", "text": "I will send the revised budget by Thursday."},
            {"id": "m2", "timestamp": "2026-10-09 10:17", "sender": "Dev", "text": "Decision: use the smaller venue."},
        ]
        analysis = analyze_dashboard_chunk("qwen2.5:3b", messages, "Maya")
        self.assertTrue(analysis["summary"])
        self.assertIsInstance(analysis["findings"], list)
        valid_ids = {message["id"] for message in messages}
        for finding in analysis["findings"]:
            self.assertTrue(finding["evidence"])
            self.assertTrue(set(finding["evidence"]).issubset(valid_ids))

        answer = answer_question_chunk("qwen2.5:3b", "What will Maya do?", "Maya", messages)
        self.assertIsNotNone(answer)
        self.assertTrue(answer["answer"])
        self.assertTrue(answer["evidence"])
        self.assertTrue(set(answer["evidence"]).issubset(valid_ids))


if __name__ == "__main__":
    unittest.main()
