import unittest

from product_logic import (derive_explicit_actions, extract_direct_mentions, extract_meetings,
                           merge_dashboard_findings, redact_phone_numbers, sanitize_generated_text,
                           score_priority)


class ProductLogicTests(unittest.TestCase):
    def setUp(self):
        self.messages = [
            {"id": "m1", "timestamp": "10:00", "sender": "Maya", "text": "@Dev please send the draft by tomorrow, urgent."},
            {"id": "m2", "timestamp": "10:02", "sender": "Lee", "text": "The venue meeting is Friday."},
            {"id": "m3", "timestamp": "10:03", "sender": "Maya", "text": "Dev, we decided to use the smaller venue."},
        ]

    def test_priority_is_deterministic_and_explained(self):
        finding = {"category": "action", "owner": "Dev", "due": "tomorrow", "evidence": ["m1"]}
        first = score_priority(finding, self.messages)
        second = score_priority(finding, self.messages)
        self.assertEqual(first, second)
        self.assertEqual(first["level"], "high")
        self.assertEqual(first["score"], 5)
        self.assertIn("Urgency is stated in the source", first["reasons"])

    def test_no_evidence_of_urgency_scores_low(self):
        finding = {"category": "action", "owner": "", "due": "", "evidence": ["m2"]}
        result = score_priority(finding, self.messages)
        self.assertEqual(result["level"], "low")
        self.assertEqual(result["reasons"], ["No explicit urgency, deadline, or owner was found"])

    def test_lower_priority_other_updates_are_scored_and_retained(self):
        finding = {"category": "other_update", "title": "Shared guide", "evidence": ["m2"], "owner": "", "due": ""}
        result = score_priority(finding, self.messages)
        self.assertEqual(result["level"], "low")
        self.assertIn("Lower-priority update retained for review", result["reasons"])
        merged = merge_dashboard_findings([{
            **finding, "confidence": "medium", "detail": "A useful resource was shared.", "when": "", "conflictEvidence": []
        }])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["category"], "other_update")

    def test_duplicate_other_updates_merge_and_keep_source_references(self):
        merged = merge_dashboard_findings([
            {"category": "other_update", "title": "Schedule changed", "confidence": "high", "evidence": ["m1"], "conflictEvidence": []},
            {"category": "other_update", "title": "Schedule changed", "confidence": "medium", "evidence": ["m2"], "conflictEvidence": []},
        ])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["evidence"], ["m1", "m2"])

    def test_duplicate_findings_merge_evidence(self):
        findings = [
            {"category": "action", "title": "Send the revised draft", "owner": "Dev", "due": "", "when": "", "confidence": "high", "evidence": ["m1"], "conflictEvidence": []},
            {"category": "action", "title": "Send the revised draft", "owner": "", "due": "", "when": "", "confidence": "medium", "evidence": ["m2"], "conflictEvidence": []},
        ]
        merged = merge_dashboard_findings(findings)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["evidence"], ["m1", "m2"])
        self.assertEqual(merged[0]["owner"], "Dev")
        self.assertEqual(merged[0]["confidence"], "medium")

    def test_conflicting_decision_sources_mark_both_for_review(self):
        findings = [
            {"category": "decision", "title": "Use the smaller venue", "confidence": "high", "evidence": ["m3"], "conflictEvidence": ["m2"]},
            {"category": "decision", "title": "Use the larger venue", "confidence": "high", "evidence": ["m2"], "conflictEvidence": []},
        ]
        marked = merge_dashboard_findings(findings)
        self.assertTrue(all(item.get("conflict") for item in marked))
        self.assertTrue(all(item["confidence"] == "low" for item in marked))

    def test_direct_mentions_use_explicit_name_or_at_handle(self):
        by_name = extract_direct_mentions(self.messages, "Dev")
        by_handle = extract_direct_mentions(self.messages, "")
        self.assertEqual([item["evidence"] for item in by_name], [["m1"], ["m3"]])
        self.assertEqual([item["confidence"] for item in by_name], ["high", "medium"])
        self.assertEqual([item["evidence"] for item in by_handle], [["m1"]])
        self.assertIn("@Dev", by_handle[0]["title"])

    def test_clear_commitments_and_addressed_requests_are_retained_as_actions(self):
        messages = [
            {"id": "m1", "timestamp": "", "sender": "Maya", "text": "I’ll send the revised budget by Thursday."},
            {"id": "m2", "timestamp": "", "sender": "Lee", "text": "@Dev please confirm the booking today."},
        ]
        findings = derive_explicit_actions(messages)
        self.assertEqual([item["evidence"] for item in findings], [["m1"], ["m2"]])
        self.assertEqual(findings[0]["owner"], "Maya")
        self.assertEqual(findings[0]["due"], "by Thursday")
        self.assertEqual(findings[1]["owner"], "Dev")

    def test_explicit_meeting_and_verbatim_time_are_retained(self):
        messages = [
            {"id": "m1", "timestamp": "", "sender": "Maya", "text": "The project sync is Friday at 14:30."},
            {"id": "m2", "timestamp": "", "sender": "Lee", "text": "The venue is ready."},
        ]
        findings = extract_meetings(messages)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["evidence"], ["m1"])
        self.assertEqual(findings[0]["when"], "Friday")
        self.assertEqual(findings[0]["confidence"], "medium")

    def test_phone_numbers_are_masked_without_masking_dates_or_source_ids(self):
        text = "Call +1 (415) 555-0137 or 020 7946 0958. Source m12 at 2026-10-09 14:30."
        masked = redact_phone_numbers(text)
        self.assertEqual(masked.count("[phone number]"), 2)
        self.assertIn("m12", masked)
        self.assertIn("2026-10-09 14:30", masked)
        self.assertNotIn("555-0137", masked)

    def test_supplied_identity_is_not_echoed_in_generated_text(self):
        self.assertEqual(
            sanitize_generated_text("Maya should call +1 415 555 0137", "@Maya"),
            "you should call [phone number]",
        )


if __name__ == "__main__":
    unittest.main()
