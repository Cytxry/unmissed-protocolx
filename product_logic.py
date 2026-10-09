"""Deterministic, explainable handling of local-model findings."""

from __future__ import annotations

import re
from difflib import SequenceMatcher


CATEGORIES = {"action", "meeting", "decision", "mention", "unanswered", "moment", "other_update"}
CONFIDENCE_LEVELS = {"high", "medium", "low"}
PHONE_NUMBER_PATTERN = re.compile(
    r"(?<![\w])(?:\+\d{1,3}[ .-]?)?(?:\(?\d{2,4}\)?[ .-]){1,3}\d{3,4}(?![\w])|"
    r"(?<![\w])\+?\d{7,15}(?![\w])"
)

QUICK_QUESTIONS = [
    {"id": "meetings", "label": "Meetings I missed", "question": "Which meetings did I miss or need to know about?"},
    {"id": "actions", "label": "What do I need to do?", "question": "What do I need to do next?"},
    {"id": "mentions", "label": "Did anyone mention me?", "question": "Did anyone mention me or my name?"},
    {"id": "decisions", "label": "Decisions made", "question": "What decisions were made?"},
    {"id": "interesting", "label": "Anything interesting?", "question": "Is there anything interesting or important I missed?"},
]


def redact_phone_numbers(value: str) -> str:
    """Mask phone-like digit sequences in generated or diagnostic text."""
    return PHONE_NUMBER_PATTERN.sub("[phone number]", value)


def sanitize_generated_text(value: str, user_identity: str = "") -> str:
    """Redact phone numbers and avoid echoing the supplied identity in generated text."""
    safe = redact_phone_numbers(value)
    identity = user_identity.strip().lstrip("@")
    if len(identity) >= 2:
        escaped = re.escape(identity)
        possessive = re.compile(rf"(?<![\w@])@?{escaped}(?:['’]s)(?!\w)", re.IGNORECASE)
        safe = possessive.sub("your", safe)
        subject_verb = re.compile(rf"(?<![\w@])@?{escaped}\s+(was|is|has|does)\b", re.IGNORECASE)
        verb_forms = {"was": "were", "is": "are", "has": "have", "does": "do"}
        safe = subject_verb.sub(lambda match: f"you {verb_forms[match.group(1).lower()]}", safe)
        identity_pattern = re.compile(rf"(?<![\w@])@?{escaped}(?!\w)", re.IGNORECASE)
        safe = identity_pattern.sub("you", safe)
    return safe


def _normalized_title(title: str) -> str:
    return re.sub(r"\W+", " ", title.casefold()).strip()


def score_priority(finding: dict, messages: list[dict]) -> dict:
    """Rank without suppressing findings; each reason is tied to source text or assignment."""
    by_id = {message["id"]: message for message in messages}
    cited = [by_id[item] for item in finding.get("evidence", []) if item in by_id]
    source = "\n".join(f"{item['sender']}: {item['text']}" for item in cited)
    score = 0
    reasons: list[str] = []
    if re.search(r"\b(urgent|asap|immediately|overdue|time[- ]sensitive|warning|risk|cancelled|canceled|moved|changed|by (?:today|tomorrow|tonight))\b", source, re.I):
        score += 2
        reasons.append("Urgency is stated in the source")
    due = str(finding.get("due", "")).strip()
    if due and due.casefold() in source.casefold():
        score += 2
        reasons.append(f"Deadline is stated: {due}")
    owner = str(finding.get("owner", "")).strip()
    if owner:
        score += 1
        reasons.append(f"Assigned to {owner}")
    if finding.get("category") == "unanswered":
        score += 1
        reasons.append("The conversation marks this request as unanswered")
    if finding.get("category") not in {"action", "unanswered"} and not reasons:
        reasons.append("Lower-priority update retained for review")
    level = "high" if score >= 3 else "medium" if score >= 1 else "low"
    if not reasons:
        reasons.append("No explicit urgency, deadline, or owner was found")
    return {"score": score, "level": level, "reasons": reasons}


def extract_direct_mentions(messages: list[dict], user_name: str = "") -> list[dict]:
    """Find literal @handles or an explicitly supplied user name in message text."""
    target = user_name.strip().lstrip("@")
    target_pattern = re.compile(rf"(?<!\w)@?{re.escape(target)}(?!\w)", re.IGNORECASE) if target else None
    handle_pattern = re.compile(r"(?<!\w)@[\w.-]{2,40}", re.UNICODE)
    findings = []
    for message in messages:
        text = message["text"]
        matches = [target_pattern.search(text)] if target_pattern else handle_pattern.findall(text)
        if not any(matches):
            continue
        label = "you" if target_pattern else matches[0]
        is_handle = bool(target and re.search(rf"(?<!\w)@{re.escape(target)}(?!\w)", text, re.IGNORECASE))
        findings.append({
            "category": "mention",
            "title": "You were directly mentioned" if target_pattern else f"Direct mention of {label}",
            "detail": "Your supplied name or handle appears in this message." if target_pattern else "An explicit handle appears in this message.",
            "owner": "",
            "due": "",
            "when": "",
            "confidence": "high" if is_handle else "medium" if target_pattern else "low",
            "evidence": [message["id"]],
            "conflictEvidence": [],
        })
    return findings


def derive_explicit_actions(messages: list[dict]) -> list[dict]:
    """Catch clear first-person commitments and addressed requests missed by extraction."""
    commitment = re.compile(
        r"\b(?:I|we)\s+(?:will|shall|can|am going to)\s+(?:send|share|review|prepare|update|confirm|book|check|deliver|finish|schedule|contact|follow up|create|submit|bring|call|write|pay)\b|"
        r"\b(?:I|we)[’']ll\s+(?:send|share|review|prepare|update|confirm|book|check|deliver|finish|schedule|contact|follow up|create|submit|bring|call|write|pay)\b",
        re.IGNORECASE,
    )
    request = re.compile(
        r"(?:@(?P<at>[\w.-]{1,40})\s+)?(?:please|could you|can you|would you)\s+"
        r"(?:send|share|review|prepare|update|confirm|book|check|deliver|finish|schedule|contact|follow up|create|submit|bring|call|write|pay)\b",
        re.IGNORECASE,
    )
    deadline = re.compile(r"\b(?:by|before|until|on)\s+(?:today|tomorrow|tonight|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b", re.IGNORECASE)
    standalone_deadline = re.compile(r"\b(?:today|tomorrow|tonight)\b", re.IGNORECASE)
    findings = []
    for message in messages:
        text = message["text"]
        assigned = commitment.search(text)
        requested = request.search(text)
        if not assigned and not requested:
            continue
        owner = message["sender"].strip() if assigned and re.search(r"\bI(?:\s|[’'])", text, re.IGNORECASE) else ""
        if requested and requested.group("at"):
            owner = requested.group("at")
        due_match = deadline.search(text) or standalone_deadline.search(text)
        findings.append({
            "category": "action",
            "title": text.strip()[:120],
            "detail": text.strip(),
            "owner": owner,
            "due": due_match.group(0) if due_match else "",
            "when": "",
            "confidence": "high",
            "evidence": [message["id"]],
            "conflictEvidence": [],
        })
    return findings


def extract_meetings(messages: list[dict]) -> list[dict]:
    """Keep explicit meeting/event references visible even when model extraction misses one."""
    terms = re.compile(r"\b(meeting|meet-up|meetup|sync|stand[- ]?up|1:1|appointment|review session|demo|kickoff|catch[- ]up|conference call)\b|\b(?:let's|lets|can we|shall we) meet\b", re.IGNORECASE)
    time_pattern = re.compile(
        r"\b(?:today|tomorrow|tonight|this (?:morning|afternoon|evening|week)|next (?:week|Monday|Tuesday|Wednesday|Thursday|Friday)|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|\d{1,2}:\d{2}(?:\s*[APap][Mm])?|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b",
        re.IGNORECASE,
    )
    findings = []
    for message in messages:
        text = message["text"]
        if not terms.search(text):
            continue
        when_match = time_pattern.search(text)
        findings.append({
            "category": "meeting",
            "title": text.strip()[:120],
            "detail": text.strip(),
            "owner": "",
            "due": "",
            "when": when_match.group(0) if when_match else "",
            "confidence": "medium",
            "evidence": [message["id"]],
            "conflictEvidence": [],
        })
    return findings


def merge_dashboard_findings(findings: list[dict]) -> list[dict]:
    """Merge repeated chunk findings, retaining all citations and cautious confidence."""
    merged: list[dict] = []
    for finding in findings:
        title_key = _normalized_title(finding.get("title", ""))
        target = next((existing for existing in merged
                       if existing.get("category") == finding.get("category")
                       and (_normalized_title(existing.get("title", "")) == title_key
                            or (set(existing.get("evidence", [])) & set(finding.get("evidence", []))
                                and SequenceMatcher(None, _normalized_title(existing.get("title", "")), title_key).ratio() >= 0.88))), None)
        if target is None:
            merged.append({**finding,
                           "evidence": list(dict.fromkeys(finding.get("evidence", []))),
                           "conflictEvidence": list(dict.fromkeys(finding.get("conflictEvidence", [])))})
            continue
        target["evidence"] = list(dict.fromkeys(target["evidence"] + finding.get("evidence", [])))
        target["conflictEvidence"] = list(dict.fromkeys(target["conflictEvidence"] + finding.get("conflictEvidence", [])))
        target["owner"] = target.get("owner") or finding.get("owner", "")
        target["due"] = target.get("due") or finding.get("due", "")
        target["when"] = target.get("when") or finding.get("when", "")
        if "low" in {target.get("confidence"), finding.get("confidence")}:
            target["confidence"] = "low"
        elif "medium" in {target.get("confidence"), finding.get("confidence")}:
            target["confidence"] = "medium"
    cited_conflicts = [item for item in merged if item.get("conflictEvidence")]
    for item in cited_conflicts:
        item["conflict"] = True
        item["confidence"] = "low"
        item["conflictNote"] = "The cited messages may contradict or supersede this update; review both sources."
    for item in merged:
        for other in merged:
            if item is other:
                continue
            if (set(item.get("conflictEvidence", [])) & set(other.get("evidence", []))
                    or set(other.get("conflictEvidence", [])) & set(item.get("evidence", []))):
                for side in (item, other):
                    side["conflict"] = True
                    side["confidence"] = "low"
                    side["conflictNote"] = "The conversation contains potentially conflicting or superseded updates; review both sources."
    decision_findings = [item for item in merged if item.get("category") == "decision"]
    for item in decision_findings:
        if item.get("conflictEvidence"):
            item["conflict"] = True
            item["confidence"] = "low"
            item["conflictNote"] = "The model found messages that may contradict this decision; review both sources."
    return merged


EXPLICIT_CHANGE_PATTERN = re.compile(
    r"\b(?:changed|moved|switched|relocated|rescheduled|shifted)\b.{0,100}?\bfrom\s+([^,.;!?\n]{1,80}?)\s+to\s+([^,.;!?\n]{1,80})",
    re.IGNORECASE,
)


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(phrase.strip())}(?!\w)", text, re.IGNORECASE))


def _explicit_changes(messages: list[dict]) -> list[dict]:
    changes = []
    for position, message in enumerate(messages):
        match = EXPLICIT_CHANGE_PATTERN.search(message.get("text", ""))
        if not match:
            continue
        before, after = (part.strip(" \t\"'“”‘’") for part in match.groups())
        if not before or not after or before.casefold() == after.casefold():
            continue
        prior_ids = [
            previous["id"] for previous in messages[:position]
            if _contains_phrase(previous.get("text", ""), before)
        ]
        changes.append({"message": message, "position": position, "before": before,
                        "after": after, "priorIds": prior_ids})
    return changes


def reconcile_explicit_changes(findings: list[dict], messages: list[dict]) -> list[dict]:
    """Retain explicit later states and mark cited earlier states as superseded."""
    positions = {message["id"]: index for index, message in enumerate(messages)}
    by_id = {message["id"]: message for message in messages}
    reconciled = [
        {**finding, "evidence": list(finding.get("evidence", [])),
         "conflictEvidence": list(finding.get("conflictEvidence", []))}
        for finding in findings
    ]
    for change in _explicit_changes(messages):
        before, after = change["before"], change["after"]
        change_id = change["message"]["id"]
        represented = False
        for finding in reconciled:
            finding_text = f"{finding.get('title', '')} {finding.get('detail', '')}"
            cited_before = [
                source for source in finding.get("evidence", [])
                if source in positions and positions[source] < change["position"]
                and _contains_phrase(by_id[source].get("text", ""), before)
            ]
            if cited_before and _contains_phrase(finding_text, before) and not _contains_phrase(finding_text, after):
                finding["conflictEvidence"] = list(dict.fromkeys(finding["conflictEvidence"] + [change_id]))
            if change_id in finding.get("evidence", []) and _contains_phrase(finding_text, after):
                finding["conflictEvidence"] = list(dict.fromkeys(
                    finding["conflictEvidence"] + change["priorIds"]
                ))
                if finding.get("category") in {"other_update", "decision", "meeting"}:
                    represented = True
        if not represented:
            reconciled.append({
                "category": "other_update",
                "title": f"Explicit change from {before} to {after}",
                "detail": f"A later message explicitly changes this from {before} to {after}.",
                "owner": "", "due": "", "when": "", "confidence": "high",
                "evidence": [change_id], "conflictEvidence": change["priorIds"],
            })
    return merge_dashboard_findings(reconciled)


def reconcile_summary_with_explicit_changes(summary: str, messages: list[dict]) -> str:
    """Prevent a no-change or stale summary from contradicting an explicit later update."""
    changes = _explicit_changes(messages)
    if not changes:
        return summary
    latest = changes[-1]
    before, after = latest["before"], latest["after"]
    no_change_claim = re.compile(r"\bno\b.{0,60}\b(?:changes?|updates?|moves?|cancellations?)\b", re.IGNORECASE)
    sentences = re.split(r"(?<=[.!?])\s+", summary.strip())
    retained = [
        sentence for sentence in sentences
        if sentence and not no_change_claim.search(sentence)
        and not (_contains_phrase(sentence, before) and not _contains_phrase(sentence, after))
    ]
    if _contains_phrase(summary, after) and not no_change_claim.search(summary):
        return summary
    update = f"Explicit update: the conversation changes from {before} to {after}."
    return " ".join([update, *retained]).strip()[:900]
