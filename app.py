#!/usr/bin/env python3
"""Local chat analysis demo. Uses only Python's standard library."""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from copy import deepcopy
from difflib import SequenceMatcher
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from analysis_prompts import (
    ANALYSIS_RETRY_PROMPT,
    ANALYSIS_PROMPT,
    ANALYSIS_RESPONSE_SCHEMA,
    QUESTION_RESPONSE_SCHEMA,
    QUESTION_SYNTHESIS_PROMPT,
    QUESTION_PROMPT,
    SUMMARY_PROMPT,
    SYNTHESIS_RESPONSE_SCHEMA,
    SYSTEM_ANALYSIS_PROMPT,
    SYSTEM_QUESTION_PROMPT,
    SYSTEM_QUESTION_SYNTHESIS_PROMPT,
    SYSTEM_SUMMARY_PROMPT,
)
from product_logic import (
    CATEGORIES,
    CONFIDENCE_LEVELS,
    QUICK_QUESTIONS,
    derive_explicit_actions,
    extract_direct_mentions,
    extract_meetings,
    merge_dashboard_findings,
    redact_phone_numbers,
    sanitize_generated_text,
    score_priority,
)


ROOT = Path(__file__).resolve().parent
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
MAX_BODY = 20 * 1024 * 1024
MAX_TEXT = 12 * 1024 * 1024
CHUNK_CHARS = 5000
CHUNK_OVERLAP = 2
JOB_TTL_SECONDS = 24 * 60 * 60
MAX_RETAINED_JOBS = 12
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
LOGGER = logging.getLogger("unmissed")


class UserError(Exception):
    pass


class OllamaOutputError(UserError):
    """Ollama answered, but its response was not complete usable JSON output."""


def validate_local_ollama_url(url: str | None = None) -> None:
    """Require a loopback Ollama endpoint before sending any conversation data."""
    target = url or OLLAMA_URL
    try:
        parsed = urlsplit(target)
        hostname = parsed.hostname or ""
        local_host = hostname.lower() == "localhost" or ip_address(hostname).is_loopback
    except ValueError:
        local_host = False
        parsed = urlsplit("")
    if parsed.scheme not in {"http", "https"} or not local_host or parsed.username or parsed.password:
        raise UserError("Ollama must use a local loopback endpoint. Conversation data was not sent.")


def public_job_data(job: dict) -> dict:
    """Return public job fields without private in-process matching data."""
    return {key: value for key, value in job.items() if not key.startswith("_")}


def prune_jobs(now: float | None = None) -> None:
    """Expire old results and cap retained jobs without removing active QA sources."""
    current = time.monotonic() if now is None else now
    with JOBS_LOCK:
        pinned_sources = {
            job.get("sourceJobId") for job in JOBS.values()
            if job.get("state") in {"queued", "running", "done"} and job.get("sourceJobId")
        }
        finished = [
            (float(job.get("_createdAt", current)), job_id)
            for job_id, job in JOBS.items()
            if job.get("state") in {"done", "error"} and job_id not in pinned_sources
        ]
        for created_at, job_id in finished:
            if current - created_at > JOB_TTL_SECONDS:
                JOBS.pop(job_id, None)
        remaining = sorted(
            (created_at, job_id) for created_at, job_id in finished if job_id in JOBS
        )
        while len(remaining) > MAX_RETAINED_JOBS:
            _, oldest_id = remaining.pop(0)
            JOBS.pop(oldest_id, None)


def question_needs_user_identity(question: str) -> bool:
    """Only include the supplied identity for mention or personal assignment queries."""
    return bool(re.search(
        r"\b(?:mention(?:ed)?|assigned|my tasks?|what do i need to do|what was i asked|asked me)\b",
        question,
        re.IGNORECASE,
    ))


def open_local_ollama(request: Request, timeout: int):
    """Open a loopback Ollama request without honoring external proxy settings."""
    validate_local_ollama_url()
    opener = build_opener(ProxyHandler({}))
    return opener.open(request, timeout=timeout)


def parse_transcript_with_warnings(raw: str) -> tuple[list[dict], list[str]]:
    """Parse common plain-text chat headers while retaining unrecognized content."""
    if not raw.strip():
        raise UserError("The transcript is empty. Paste a conversation or choose a .txt file.")
    if len(raw) > MAX_TEXT:
        raise UserError("This transcript is over the 12 MB text limit. Split it into smaller files.")

    # Generic bracket/ISO timestamps plus the common date-and-time form seen in chat exports.
    patterns = [
        re.compile(r"^\[(?P<ts>[^\]]{1,80})\][ \t]*(?P<rest>.*)$"),
        re.compile(r"^(?P<ts>\d{4}-\d\d-\d\d[ T]\d\d:\d\d(?::\d\d)?(?:\s*[+-]\d\d:?\d\d|\s*[A-Z]{2,5})?)\s*[-–—,]\s*(?P<rest>.*)$"),
        re.compile(r"^(?P<ts>\d{1,2}/\d{1,2}/\d{2,4},?\s+\d{1,2}:\d\d(?::\d\d)?\s*(?:[APap][Mm])?)\s*[-–—]\s*(?P<rest>.*)$"),
    ]
    speaker = re.compile(r"^(?P<sender>[^:\n]{1,120}):[ \t]?(?P<text>.*)$")
    system_actor = re.compile(r"^(?P<sender>.+?)\s+(?P<text>(?:changed\b|added\b|removed\b|left\b|joined\b|created\b|deleted\b|turned on\b|turned off\b).*)$", re.IGNORECASE)
    system_notice = re.compile(
        r"^(?:messages and calls are end-to-end encrypted\b.*|this group was created by .+|you (?:created|were added to|joined) .+)$",
        re.IGNORECASE,
    )
    messages: list[dict] = []
    warnings: list[str] = []
    unparsed_lines: list[int] = []
    current: dict | None = None
    for line_number, line in enumerate(raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"), 1):
        match = next((found for pattern in patterns if (found := pattern.match(line))), None)
        timestamp = ""
        content = line
        if match:
            timestamp = match.group("ts").strip()
            content = match.group("rest")
        sm = speaker.match(content)
        if sm:
            if current:
                messages.append(current)
            current = {"id": "", "timestamp": timestamp,
                       "sender": sm.group("sender").strip(), "text": sm.group("text")}
        elif line.strip() and timestamp:
            # Timestamped lines without a speaker are commonly system notifications.
            if current:
                messages.append(current)
            actor = system_actor.match(content)
            current = {"id": "", "timestamp": timestamp,
                       "sender": actor.group("sender").strip() if actor else "System",
                       "text": content}
        elif line.strip() and system_actor.match(line):
            if current:
                messages.append(current)
            actor = system_actor.match(line)
            current = {"id": "", "timestamp": "", "sender": actor.group("sender").strip(), "text": line}
        elif line.strip() and system_notice.match(line):
            if current:
                messages.append(current)
            current = {"id": "", "timestamp": "", "sender": "System", "text": line}
        elif line.strip():
            if current:
                current["text"] += "\n" + line
                if not line[:1].isspace():
                    unparsed_lines.append(line_number)
            else:
                # Preserve leading malformed/unlabelled content instead of rejecting the chat.
                current = {"id": "", "timestamp": "", "sender": "Unknown", "text": line}
                unparsed_lines.append(line_number)
    if current:
        messages.append(current)
    if not messages:
        raise UserError("No messages or conversation text were found. Paste a conversation or choose a text file.")
    for idx, msg in enumerate(messages, 1):
        msg["id"] = f"m{idx}"
    if unparsed_lines:
        line_list = ", ".join(str(n) for n in unparsed_lines[:10])
        suffix = " …" if len(unparsed_lines) > 10 else ""
        warnings.append(
            f"Some lines did not match a known message header (line {line_list}{suffix}); "
            "they were preserved as standalone text or attached to the preceding message."
        )
    return messages, warnings


def parse_transcript(raw: str) -> list[dict]:
    """Backward-compatible parser entry point returning messages only."""
    return parse_transcript_with_warnings(raw)[0]


def make_chunks(messages: list[dict]) -> list[list[dict]]:
    costs = [len(m["text"]) + len(m["sender"]) + len(m["timestamp"]) + 32 for m in messages]
    chunks: list[list[dict]] = []
    start = 0
    while start < len(messages):
        end = start
        size = 0
        while end < len(messages) and (size + costs[end] <= CHUNK_CHARS or end == start):
            size += costs[end]
            end += 1
        chunks.append(messages[start:end])
        if end == len(messages):
            break
        # Keep useful context without letting overlap dominate small chunks.
        overlap = min(CHUNK_OVERLAP, max(1, (end - start) // 3))
        next_start = max(start + 1, end - overlap)
        while next_start < end and sum(costs[next_start:end]) + costs[end] > CHUNK_CHARS:
            next_start += 1
        start = next_start
    return chunks


def ollama_tags() -> list[str]:
    try:
        validate_local_ollama_url()
        req = Request(f"{OLLAMA_URL}/api/tags", headers={"Accept": "application/json"})
        with open_local_ollama(req, timeout=4) as response:
            data = json.loads(response.read().decode("utf-8"))
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


def ollama_json(model: str, system_prompt: str, user_prompt: str, response_schema: dict | None = None) -> dict:
    """Run one JSON-mode request against the configured local Ollama server."""
    validate_local_ollama_url()
    body = json.dumps({"model": model, "stream": False, "format": response_schema or "json", "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ], "options": {"temperature": 0.1}}).encode("utf-8")
    req = Request(f"{OLLAMA_URL}/api/chat", data=body, headers={"Content-Type": "application/json"}, method="POST")
    started = time.monotonic()
    response_chars = 0
    try:
        with open_local_ollama(req, timeout=240) as response:
            payload = json.loads(response.read().decode("utf-8"))
        done_reason = str(payload.get("done_reason", "unknown"))
        if payload.get("done") is False or done_reason in {"length", "max_tokens"}:
            raise OllamaOutputError(f"Ollama stopped before completing its response (done_reason={done_reason}).")
        content = payload.get("message", {}).get("content", "")
        response_chars = len(content) if isinstance(content, str) else 0
        if not isinstance(content, str) or not content.strip():
            raise OllamaOutputError(f"Ollama returned an empty response (done_reason={done_reason}).")
        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            raise OllamaOutputError(f"Ollama returned malformed JSON (done_reason={done_reason}): {exc.msg}.") from exc
        if not isinstance(result, dict):
            raise OllamaOutputError(f"Ollama returned {type(result).__name__}, expected a JSON object (done_reason={done_reason}).")
        LOGGER.info("ollama_request_complete model=%s prompt_chars=%d response_chars=%d elapsed_s=%.2f",
                    model, len(user_prompt), response_chars, time.monotonic() - started)
        return result
    except HTTPError as exc:
        detail = redact_phone_numbers(exc.read().decode("utf-8", "replace")[:500])
        if exc.code == 404:
            raise UserError(f"Ollama couldn't find model ‘{model}’. Pull it with ‘ollama pull {model}’, then retry.")
        raise UserError(f"Ollama returned HTTP {exc.code}: {detail or 'request failed'}") from exc
    except (URLError, TimeoutError) as exc:
        raise UserError(f"Couldn't reach Ollama at {OLLAMA_URL}. Start Ollama and confirm a model is available. Details: {exc}") from exc
    except OllamaOutputError as exc:
        LOGGER.warning("ollama_output_invalid error_type=%s response_chars=%d elapsed_s=%.2f",
                       type(exc).__name__, response_chars, time.monotonic() - started)
        raise
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        raise UserError(f"Ollama returned an unreadable response. Retry the analysis. Details: {exc}") from exc


def analyze_chunk(model: str, messages: list[dict]) -> list[dict]:
    transcript = "\n".join(
        f"[{m['id']}] {m['timestamp'] + ' ' if m['timestamp'] else ''}{m['sender']}: {m['text']}"
        for m in messages
    )
    prompt = f"""Read this conversation chunk. Extract every actionable task and explicit or strongly implied decision. A commitment like “I will…” or “I’ll…” is a task; use that speaker as the owner. A choice or agreement is a decision. Keep distinct tasks as separate findings.
Return a JSON object exactly shaped as {{"findings":[{{"type":"task"|"decision","title":"short clear statement","owner":"person or empty string","due":"date or empty string","evidence":["message id"]}}]}}.
Use only the supplied message IDs as evidence. Cite the message IDs that support each finding. Do not invent owners, dates, or findings. If there are none, return an empty findings array. Keep findings concise. Output JSON only.

Conversation:
{transcript}"""
    body = json.dumps({"model": model, "stream": False, "format": "json", "messages": [
        {"role": "system", "content": "You extract tasks and decisions from conversation transcripts. Be faithful to the supplied text."},
        {"role": "user", "content": prompt},
    ], "options": {"temperature": 0.1}}).encode("utf-8")
    req = Request(f"{OLLAMA_URL}/api/chat", data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with open_local_ollama(req, timeout=240) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload.get("message", {}).get("content", "")
        result = json.loads(content)
        if not isinstance(result.get("findings"), list):
            raise ValueError("The model response did not contain a findings list.")
        message_by_id = {m["id"]: m for m in messages}
        valid_ids = set(message_by_id)
        normalized = []
        for item in result["findings"]:
            if not isinstance(item, dict) or item.get("type") not in ("task", "decision"):
                continue
            title = str(item.get("title", "")).strip()
            if not title:
                continue
            evidence = list(dict.fromkeys(x for x in item.get("evidence", []) if isinstance(x, str) and x in valid_ids))
            if not evidence:
                continue
            evidence_text = "\n".join(message_by_id[x]["sender"] + ": " + message_by_id[x]["text"] for x in evidence)
            # Ground model metadata in its cited messages; the model may normalize or infer dates incorrectly.
            owner = str(item.get("owner", "")).strip()
            if owner and not re.search(rf"(?<!\w){re.escape(owner)}(?!\w)", evidence_text, re.IGNORECASE):
                owner = ""
            due = str(item.get("due", "")).strip()
            if due and due.casefold() not in evidence_text.casefold():
                due = ""
            kind = item["type"]
            commitment = re.compile(r"\b(?:i|we)\s+(?:will|can|shall|am going to)\s+(?:send|update|confirm|share|review|prepare|book|create|check|deliver|finish|schedule|contact|follow up)\b|\b(?:i'll|we'll)\s+(?:send|update|confirm|share|review|prepare|book|create|check|deliver|finish|schedule|contact|follow up)\b", re.IGNORECASE)
            if commitment.search(evidence_text):
                kind = "task"
            if kind == "decision":
                owner = ""
                due = ""
            normalized.append({"type": kind, "title": title, "owner": owner,
                               "due": due, "evidence": evidence})
        return normalized
    except HTTPError as exc:
        detail = redact_phone_numbers(exc.read().decode("utf-8", "replace")[:500])
        if exc.code == 404:
            raise UserError(f"Ollama couldn't find model ‘{model}’. Pull it with ‘ollama pull {model}’, then retry.")
        raise UserError(f"Ollama returned HTTP {exc.code}: {detail or 'request failed'}") from exc
    except (URLError, TimeoutError) as exc:
        raise UserError(f"Couldn't reach Ollama at {OLLAMA_URL}. Start Ollama and confirm a model is available. Details: {exc}") from exc
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        raise UserError(f"Ollama returned an unreadable response. Retry the analysis. Details: {exc}") from exc


def _format_messages(messages: list[dict]) -> str:
    return "\n".join(
        f"SOURCE_ID={m['id']} | TIMESTAMP={m['timestamp'] or '(none)'} | SENDER={m['sender']} | TEXT={m['text']}"
        for m in messages
    )


def _schema_with_evidence_ids(schema: dict, message_ids: set[str]) -> dict:
    """Constrain model citations to actual IDs while leaving category strings open-ended."""
    constrained = deepcopy(schema)
    allowed_ids = sorted(message_ids)
    if "findings" in constrained["properties"]:
        item_schema = constrained["properties"]["findings"]["items"]["properties"]
        item_schema["evidence"]["items"]["enum"] = allowed_ids
        item_schema["conflictEvidence"]["items"]["enum"] = allowed_ids
    else:
        constrained["properties"]["evidence"]["items"]["enum"] = allowed_ids
    return constrained


def _validate_analysis_shape(result: dict, valid_ids: set[str]) -> None:
    """Reject incomplete schema-shaped output so it gets the one controlled retry."""
    if not isinstance(result.get("findings"), list):
        keys = ", ".join(sorted(str(key) for key in result.keys())) or "none"
        raise OllamaOutputError(f"Expected a findings array; response object keys were: {keys}.")
    if not isinstance(result.get("summary"), str) or not result["summary"].strip():
        keys = ", ".join(sorted(str(key) for key in result.keys())) or "none"
        raise OllamaOutputError(f"Expected a non-empty summary string; response object keys were: {keys}.")
    required = {"category", "title", "detail", "owner", "due", "when", "confidence", "evidence", "conflictEvidence"}
    for index, item in enumerate(result["findings"], 1):
        if not isinstance(item, dict):
            raise OllamaOutputError(f"Finding {index} was not a JSON object.")
        missing = required - item.keys()
        if missing:
            raise OllamaOutputError(f"Finding {index} omitted required fields: {', '.join(sorted(missing))}.")
        if (not isinstance(item["category"], str) or not item["category"].strip()
                or len(item["category"]) > 40
                or not isinstance(item["title"], str) or not item["title"].strip()):
            raise OllamaOutputError(f"Finding {index} had an invalid category or empty title.")
        if any(not isinstance(item[key], str) for key in ("detail", "owner", "due", "when")):
            raise OllamaOutputError(f"Finding {index} had a non-text detail or metadata field.")
        if not isinstance(item["confidence"], str) or item["confidence"] not in CONFIDENCE_LEVELS:
            raise OllamaOutputError(f"Finding {index} had an invalid confidence value.")
        if not isinstance(item["evidence"], list) or not item["evidence"] or any(not isinstance(source, str) for source in item["evidence"]):
            raise OllamaOutputError(f"Finding {index} did not contain a non-empty evidence ID array.")
        if not any(source in valid_ids for source in item["evidence"]):
            raise OllamaOutputError(f"Finding {index} cited no message ID in this chunk.")
        if not isinstance(item["conflictEvidence"], list) or any(not isinstance(source, str) for source in item["conflictEvidence"]):
            raise OllamaOutputError(f"Finding {index} did not contain a conflict evidence ID array.")


def normalize_analysis_findings(raw_findings: list[dict], messages: list[dict], user_name: str = "") -> list[dict]:
    """Normalize categories and retain every candidate with verifiable evidence."""
    message_by_id = {message["id"]: message for message in messages}
    valid_ids = set(message_by_id)
    normalized = []
    commitment = re.compile(
        r"\b(?:i|we)\s+(?:will|can|shall|am going to)\s+(?:send|update|confirm|share|review|prepare|book|create|check|deliver|finish|schedule|contact|follow up)\b|"
        r"\b(?:i'll|we'll)\s+(?:send|update|confirm|share|review|prepare|book|create|check|deliver|finish|schedule|contact|follow up)\b",
        re.IGNORECASE,
    )
    for item in raw_findings:
        title = str(item.get("title", "")).strip()
        raw_evidence = item.get("evidence", [])
        if isinstance(raw_evidence, str):
            raw_evidence = [raw_evidence]
        evidence = list(dict.fromkeys(
            source for source in raw_evidence
            if isinstance(source, str) and source in valid_ids
        ))
        if not title or not evidence:
            continue
        cited = [message_by_id[source] for source in evidence]
        source_text = "\n".join(f"{message['sender']}: {message['text']}" for message in cited)
        raw_category = re.sub(r"[\s-]+", "_", item["category"].strip().casefold())
        category = raw_category if raw_category in CATEGORIES else "other_update"
        if category == "mention":
            target = user_name.strip().lstrip("@")
            if target:
                relevant_mention = re.compile(rf"(?<!\w)@?{re.escape(target)}(?!\w)", re.IGNORECASE)
            else:
                relevant_mention = re.compile(r"(?<!\w)@[\w.-]{2,40}", re.UNICODE)
            if not any(relevant_mention.search(message["text"]) for message in cited):
                continue
        if commitment.search(source_text) and category in {"action", "moment", "other_update"}:
            category = "action"
        owner = str(item.get("owner", "")).strip()
        if owner and not re.search(rf"(?<!\w){re.escape(owner)}(?!\w)", source_text, re.IGNORECASE):
            owner = ""
        due = str(item.get("due", "")).strip()
        if due and due.casefold() not in source_text.casefold():
            due = ""
        when = str(item.get("when", "")).strip()
        if when and when.casefold() not in source_text.casefold():
            when = ""
        raw_conflict_evidence = item.get("conflictEvidence", [])
        if isinstance(raw_conflict_evidence, str):
            raw_conflict_evidence = [raw_conflict_evidence]
        conflict_evidence = list(dict.fromkeys(
            source for source in raw_conflict_evidence
            if isinstance(source, str) and source in valid_ids
        ))
        confidence = str(item.get("confidence", "medium")).lower()
        if confidence not in CONFIDENCE_LEVELS:
            confidence = "medium"
        normalized.append({
            "category": category,
            "title": sanitize_generated_text(title, user_name),
            "detail": sanitize_generated_text(str(item.get("detail", "")).strip(), user_name),
            "owner": "You" if sanitize_generated_text(owner, user_name).casefold() == "you" else sanitize_generated_text(owner, user_name),
            "due": sanitize_generated_text(due, user_name),
            "when": sanitize_generated_text(when, user_name),
            "confidence": confidence,
            "evidence": evidence,
            "conflictEvidence": conflict_evidence,
        })
    return normalized


def analyze_dashboard_chunk(model: str, messages: list[dict], user_name: str = "") -> dict:
    """Extract dashboard findings from a chunk and validate every source reference."""
    conversation = _format_messages(messages)
    prompt = ANALYSIS_PROMPT.replace("{user_name}", user_name or "(not supplied)").replace("{conversation}", conversation)
    valid_ids = {message["id"] for message in messages}
    response_schema = _schema_with_evidence_ids(ANALYSIS_RESPONSE_SCHEMA, valid_ids)
    result: dict | None = None
    last_output_error: OllamaOutputError | None = None
    for attempt in range(2):
        try:
            result = ollama_json(model, SYSTEM_ANALYSIS_PROMPT, prompt, response_schema)
            _validate_analysis_shape(result, valid_ids)
            break
        except OllamaOutputError as exc:
            last_output_error = exc
            if attempt == 0:
                prompt = ANALYSIS_RETRY_PROMPT.replace("{problem}", str(exc)).replace("{conversation}", conversation)
                continue
            raise UserError(f"Ollama did not return a complete analysis after one retry. Details: {exc}") from exc
    if result is None:
        raise UserError(f"Ollama did not return an analysis. Details: {last_output_error or 'empty response'}")
    normalized = normalize_analysis_findings(result["findings"], messages, user_name)
    return {"summary": sanitize_generated_text(str(result.get("summary", "")).strip(), user_name), "findings": normalized}


def _validate_question_shape(result: dict, valid_ids: set[str], source_messages: list[dict] | None = None) -> None:
    if not isinstance(result.get("answer"), str):
        raise OllamaOutputError("Question response omitted its answer string.")
    if result["answer"].strip().casefold() in CONFIDENCE_LEVELS:
        raise OllamaOutputError("Question response returned a confidence label instead of an answer.")
    if result.get("confidence") not in CONFIDENCE_LEVELS:
        raise OllamaOutputError("Question response had an invalid confidence value.")
    evidence = result.get("evidence")
    if not isinstance(evidence, list) or any(not isinstance(source, str) for source in evidence):
        raise OllamaOutputError("Question response omitted a valid evidence ID array.")
    if any(source not in valid_ids for source in evidence):
        raise OllamaOutputError("Question response cited a message outside the supplied source set.")
    if bool(result["answer"].strip()) != bool(evidence):
        raise OllamaOutputError("Question answer and evidence did not agree.")
    if result["answer"].strip() and re.match(
        r"^(?:no|nope|nothing(?:\s+(?:is|was)\s+(?:mentioned|provided|found))?|not mentioned|no one (?:mentioned|said))\s*[.!?]*$",
        result["answer"].strip(), re.IGNORECASE,
    ):
        sources = {message["id"]: message for message in (source_messages or [])}
        cited_text = " ".join(sources[source]["text"] for source in evidence if source in sources)
        explicit_negative = re.search(r"\b(?:no|not|never|none|didn't|doesn't|isn't|wasn't|weren't|cannot|can't|won't)\b", cited_text, re.IGNORECASE)
        if not explicit_negative:
            raise OllamaOutputError("Question response inferred a negative from silence instead of citing explicit negative evidence.")


def answer_question_chunk(model: str, question: str, user_name: str, messages: list[dict]) -> dict | None:
    conversation = _format_messages(messages)
    prompt = (QUESTION_PROMPT.replace("{question}", question)
              .replace("{user_name}", user_name or "(not supplied)")
              .replace("{conversation}", conversation))
    valid_ids = {message["id"] for message in messages}
    schema = _schema_with_evidence_ids(QUESTION_RESPONSE_SCHEMA, valid_ids)
    result: dict | None = None
    last_error: OllamaOutputError | None = None
    for attempt in range(2):
        try:
            result = ollama_json(model, SYSTEM_QUESTION_PROMPT, prompt, schema)
            _validate_question_shape(result, valid_ids, messages)
            break
        except OllamaOutputError as exc:
            last_error = exc
            if attempt == 0:
                prompt += f"\n\nCorrection: the previous response was incomplete ({exc}). Return the required JSON, with exact source IDs from this chunk."
                continue
            raise UserError(f"The local model could not return a complete grounded answer after one retry: {exc}") from exc
    if result is None:
        raise UserError(f"The local model returned no question answer: {last_error or 'empty response'}")
    answer = str(result.get("answer", "")).strip()
    raw_evidence = result.get("evidence", [])
    if isinstance(raw_evidence, str):
        raw_evidence = [raw_evidence]
    evidence = list(dict.fromkeys(
        source for source in raw_evidence
        if isinstance(source, str) and source in valid_ids
    ))
    if not answer or not evidence:
        return None
    confidence = str(result.get("confidence", "medium")).lower()
    if confidence not in CONFIDENCE_LEVELS:
        confidence = "medium"
    return {"answer": sanitize_generated_text(answer, user_name), "confidence": confidence, "evidence": evidence}


def synthesize_question_answers(model: str, question: str, user_name: str, answers: list[dict], messages: list[dict]) -> dict:
    """Synthesize chunk answers while independently reviewing bounded original transcript context."""
    by_id = {message["id"]: message for message in messages}
    source_lines = []
    source_ids = []
    source_chars = 0
    context_truncated = False
    for message in messages:
        line = f"SOURCE_ID={message['id']} | TIMESTAMP={message['timestamp'] or '(none)'} | SENDER={message['sender']} | TEXT={message['text']}"
        if source_chars + len(line) > 20000:
            context_truncated = True
            break
        source_lines.append(line)
        source_ids.append(message["id"])
        source_chars += len(line)
    prompt = (QUESTION_SYNTHESIS_PROMPT
              .replace("{question}", question)
              .replace("{answers}", json.dumps(answers, ensure_ascii=False))
              .replace("{sources}", "\n".join(source_lines) or "(no source messages fit the synthesis context)"))
    candidate_ids = set(source_ids)
    schema = _schema_with_evidence_ids(QUESTION_RESPONSE_SCHEMA, candidate_ids)
    last_error: OllamaOutputError | None = None
    result: dict | None = None
    for attempt in range(2):
        try:
            result = ollama_json(model, SYSTEM_QUESTION_SYNTHESIS_PROMPT, prompt, schema)
            _validate_question_shape(result, candidate_ids, messages)
            break
        except OllamaOutputError as exc:
            last_error = exc
            if attempt == 0:
                prompt += f"\n\nCorrection: the previous synthesis was incomplete ({exc}). Return the required answer JSON and exact supplied source IDs."
                continue
            raise UserError(f"The local model could not synthesize the grounded answer after one retry: {exc}") from exc
    if result is None:
        raise UserError(f"The local model returned no answer synthesis: {last_error or 'empty response'}")
    normalized = None
    if result["answer"].strip() and result["evidence"]:
        normalized = {
            "answer": sanitize_generated_text(result["answer"].strip(), user_name),
            "confidence": result["confidence"],
            "evidence": list(dict.fromkeys(source for source in result["evidence"] if source in by_id)),
        }
    return {"answer": normalized, "contextTruncated": context_truncated}


def synthesize_dashboard(model: str, summaries: list[str], findings: list[dict], messages: list[dict], user_name: str = "") -> dict:
    """Use the existing final summary pass to reconcile all chunk findings and their source evidence."""
    summary_input = "\n".join(f"- Chunk {index}: {summary}" for index, summary in enumerate(summaries, 1) if summary.strip())
    if not summary_input:
        summary_input = "- No chunk summary was available."
    by_id = {message["id"]: message for message in messages}
    cited_ids = list(dict.fromkeys(
        source for finding in findings
        for source in finding.get("evidence", []) + finding.get("conflictEvidence", [])
        if source in by_id
    ))
    # Source context is limited to keep local synthesis bounded; all candidate findings
    # and their source IDs remain present, and truncation is surfaced to the presenter.
    candidates = findings
    source_lines = []
    source_chars = 0
    context_truncated = False
    for source in cited_ids:
        message = by_id[source]
        line = f"[{source}] {message['timestamp'] + ' ' if message['timestamp'] else ''}{message['sender']}: {message['text']}"
        if source_chars + len(line) > 20000:
            context_truncated = True
            break
        source_lines.append(line)
        source_chars += len(line)
    prompt = (SUMMARY_PROMPT
              .replace("{summaries}", summary_input)
              .replace("{findings}", json.dumps(candidates, ensure_ascii=False))
              .replace("{sources}", "\n".join(source_lines) or "(no cited source messages)"))
    valid_ids = set(by_id)
    last_error: OllamaOutputError | None = None
    result = None
    for attempt in range(2):
        try:
            synthesis_ids = {source for finding in candidates
                             for source in finding.get("evidence", []) + finding.get("conflictEvidence", [])
                             if source in valid_ids}
            result = ollama_json(model, SYSTEM_SUMMARY_PROMPT, prompt,
                                 _schema_with_evidence_ids(SYNTHESIS_RESPONSE_SCHEMA, synthesis_ids))
            _validate_analysis_shape(result, valid_ids)
            break
        except OllamaOutputError as exc:
            last_error = exc
            if attempt == 0:
                prompt += f"\n\nCorrection: the prior synthesis was incomplete ({exc}). Return the required JSON object with both summary and findings; cite only supplied IDs."
                continue
            raise UserError(f"Ollama could not synthesize the chunk findings after one retry: {exc}") from exc
    if result is None:
        raise UserError(f"Ollama returned no synthesis: {last_error or 'empty response'}")
    synthesized = normalize_analysis_findings(result["findings"], messages, user_name)
    # Preserve the per-chunk findings even if the synthesis omits a valid candidate.
    merged = merge_dashboard_findings(findings + synthesized)
    return {"summary": sanitize_generated_text(result["summary"].strip(), user_name), "findings": merged,
            "contextTruncated": context_truncated}


def summarize_chunks(model: str, summaries: list[str]) -> str:
    """Compatibility helper retained for callers that only need a summary string."""
    unique = list(dict.fromkeys(summary.strip() for summary in summaries if summary.strip()))
    return " ".join(unique)[:900] if unique else "No concise summary was available from the local model."


def merge_findings(items: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for item in items:
        key = re.sub(r"\W+", " ", item["title"].lower()).strip()
        target = next((existing for existing in merged
                       if existing["type"] == item["type"]
                       and (re.sub(r"\W+", " ", existing["title"].lower()).strip() == key
                            or (set(existing["evidence"]) & set(item["evidence"])
                                and SequenceMatcher(None, re.sub(r"\W+", " ", existing["title"].lower()).strip(), key).ratio() >= 0.88))), None)
        if target is None:
            merged.append({**item, "evidence": list(item["evidence"])})
        else:
            target["evidence"] = list(dict.fromkeys(target["evidence"] + item["evidence"]))
            target["owner"] = target["owner"] or item["owner"]
            target["due"] = target["due"] or item["due"]
    return merged


def run_job(job_id: str, raw: str, model: str, user_name: str = "") -> None:
    try:
        messages, warnings = parse_transcript_with_warnings(raw)
        chunks = make_chunks(messages)
        findings: list[dict] = []
        summaries: list[str] = []
        failed_chunks: list[int] = []
        chunk_errors: list[Exception] = []
        for index, chunk in enumerate(chunks, 1):
            with JOBS_LOCK:
                JOBS[job_id].update({"state": "running", "stage": "inference", "completed": index - 1,
                                     "total": len(chunks), "message": f"Analyzing chunk {index} of {len(chunks)} with {model}…"})
            chunk_started = time.monotonic()
            try:
                result = analyze_dashboard_chunk(model, chunk, user_name)
            except Exception as exc:
                failed_chunks.append(index)
                chunk_errors.append(exc)
                LOGGER.warning("analysis_chunk_failed chunk=%d total=%d error_type=%s",
                               index, len(chunks), type(exc).__name__)
                continue
            LOGGER.info("analysis_chunk_complete chunk=%d total=%d findings=%d elapsed_s=%.2f",
                        index, len(chunks), len(result["findings"]), time.monotonic() - chunk_started)
            summaries.append(result["summary"])
            findings.extend(result["findings"])
        if not summaries:
            known_error = next((error for error in chunk_errors if isinstance(error, UserError)), None)
            if known_error:
                raise known_error
            raise UserError("Local analysis failed for every conversation section. Check Ollama and the selected model, then retry.")
        if failed_chunks:
            failed_list = ", ".join(str(index) for index in failed_chunks)
            warnings.append(
                f"Local analysis failed for section(s) {failed_list}; results cover {len(summaries)} of {len(chunks)} sections and may be incomplete."
            )
        existing_action_sources = {
            source for finding in findings if finding.get("category") == "action"
            for source in finding.get("evidence", [])
        }
        findings.extend(item for item in derive_explicit_actions(messages)
                        if not (set(item["evidence"]) & existing_action_sources))
        existing_meeting_sources = {
            source for finding in findings if finding.get("category") == "meeting"
            for source in finding.get("evidence", [])
        }
        findings.extend(item for item in extract_meetings(messages)
                        if not (set(item["evidence"]) & existing_meeting_sources))
        existing_mention_sources = {
            source for finding in findings if finding.get("category") == "mention"
            for source in finding.get("evidence", [])
        }
        findings.extend(item for item in extract_direct_mentions(messages, user_name)
                        if not (set(item["evidence"]) & existing_mention_sources))
        findings = merge_dashboard_findings(findings)
        synthesis_attempted = len(chunks) > 1 and not failed_chunks
        synthesis_complete = len(chunks) <= 1
        if len(chunks) > 1 and not failed_chunks:
            with JOBS_LOCK:
                JOBS[job_id].update({"state": "running", "stage": "summary", "completed": len(chunks),
                                     "total": len(chunks) + 1, "message": "Combining the conversation summary…"})
        try:
            if failed_chunks:
                # Do not let a final pass infer a complete cross-section story from
                # missing chunk results. Keep the successful chunk summaries visible.
                summary = " ".join(dict.fromkeys(item for item in summaries if item))[:900]
                if not summary:
                    summary = "Some conversation sections were analyzed, but no concise summary was returned."
                warnings.append("Cross-section synthesis was skipped because one or more sections failed.")
            elif len(chunks) > 1:
                synthesis = synthesize_dashboard(model, summaries, findings, messages, user_name)
                summary, findings = synthesis["summary"], synthesis["findings"]
                synthesis_complete = True
                if synthesis.get("contextTruncated"):
                    warnings.append("The final synthesis source context was shortened for a large transcript; findings remain linked to their original messages, so review sources for cross-section changes.")
            else:
                summary = summaries[0] if summaries else "No concise summary was available from the local model."
        except Exception as exc:
            LOGGER.warning("analysis_synthesis_failed error_type=%s", type(exc).__name__)
            summary = " ".join(dict.fromkeys(item for item in summaries if item))[:900]
            warnings.append("Cross-section synthesis was incomplete; findings from every analyzed section are retained, so review the source for conflicts or missing context.")
            synthesis_complete = False
        if not findings:
            if failed_chunks:
                warnings.append("No findings were extracted from the successfully analyzed sections; the unanalyzed content is not verified.")
            else:
                warnings.append("No clear findings were extracted. This does not confirm there is no important information; review the original messages.")
        for finding in findings:
            finding["priority"] = score_priority(finding, messages)
            for field in ("title", "detail", "owner", "due", "when"):
                if isinstance(finding.get(field), str):
                    finding[field] = sanitize_generated_text(finding[field], user_name)
            if finding.get("owner", "").casefold() == "you":
                finding["owner"] = "You"
            finding["priority"]["reasons"] = [
                sanitize_generated_text(reason, user_name)
                for reason in finding["priority"].get("reasons", [])
            ]
        summary = sanitize_generated_text(summary, user_name)
        warnings = [redact_phone_numbers(warning) for warning in warnings]
        coverage = {"analysisComplete": not failed_chunks, "analyzedChunks": len(summaries),
                    "totalChunks": len(chunks), "failedChunks": failed_chunks,
                    "synthesisComplete": synthesis_complete}
        with JOBS_LOCK:
            completed_steps = len(chunks) + (1 if synthesis_attempted else 0)
            JOBS[job_id].update({"state": "done", "stage": "complete", "completed": completed_steps,
                                 "total": completed_steps, "message": "Catch-up is ready.",
                                 "messages": messages, "findings": findings, "summary": summary,
                                 "model": model, "chunks": len(chunks), "_userName": user_name,
                                 "warnings": warnings, "coverage": coverage})
    except UserError as exc:
        with JOBS_LOCK:
            JOBS[job_id].update({"state": "error", "stage": "error",
                                 "message": sanitize_generated_text(str(exc), user_name)})
    except Exception as exc:
        with JOBS_LOCK:
            JOBS[job_id].update({"state": "error", "stage": "error",
                                 "message": sanitize_generated_text(f"Analysis failed: {exc}", user_name)})


def run_question(job_id: str, source_job_id: str, question: str) -> None:
    try:
        with JOBS_LOCK:
            source = JOBS.get(source_job_id)
            source = dict(source) if source else None
        if not source or source.get("state") != "done":
            raise UserError("That conversation is no longer available. Import it again to ask a question.")
        messages = source["messages"]
        model = source["model"]
        user_name = source.get("_userName", "")
        matching_identity = user_name if question_needs_user_identity(question) else ""
        chunks = make_chunks(messages)
        answers: list[dict] = []
        failed_chunks: list[int] = []
        for index, chunk in enumerate(chunks, 1):
            with JOBS_LOCK:
                JOBS[job_id].update({"state": "running", "stage": "question", "completed": index - 1,
                                     "total": len(chunks) + (1 if len(chunks) > 1 else 0), "message": f"Checking conversation section {index} of {len(chunks)}…"})
            chunk_started = time.monotonic()
            try:
                answer = answer_question_chunk(model, question, matching_identity, chunk)
            except UserError as exc:
                failed_chunks.append(index)
                LOGGER.warning("question_chunk_failed chunk=%d total=%d error_type=%s",
                               index, len(chunks), type(exc).__name__)
                if len(chunks) == 1:
                    raise
                continue
            LOGGER.info("question_chunk_complete chunk=%d total=%d has_answer=%s elapsed_s=%.2f",
                        index, len(chunks), bool(answer), time.monotonic() - chunk_started)
            if answer:
                answers.append(answer)
        warnings = []
        if failed_chunks:
            ranges = ", ".join(str(index) for index in failed_chunks)
            warnings.append(f"Per-section question analysis failed for section(s) {ranges}. The final review will inspect original messages where it can; no negative conclusion can come from the failed section checks.")
        unique_answers = list(dict.fromkeys(item["answer"] for item in answers))
        evidence = list(dict.fromkeys(source_id for item in answers for source_id in item["evidence"] if source_id in {m["id"] for m in messages}))
        if len(chunks) > 1:
            with JOBS_LOCK:
                JOBS[job_id].update({"state": "running", "stage": "synthesis", "completed": len(chunks),
                                     "total": len(chunks) + 1, "message": "Reviewing original messages and reconciling answers across the conversation…"})
            try:
                synthesis = synthesize_question_answers(model, question, matching_identity, answers, messages)
                combined = synthesis.get("answer")
                if combined:
                    if failed_chunks:
                        warnings[0] = "One or more per-section question checks failed; the final synthesis reviewed original messages. Check its citations and any context-truncation warning."
                    answer_text = combined["answer"]
                    evidence = combined["evidence"]
                    confidence = "low" if failed_chunks else combined["confidence"]
                    # Retain valid chunk answers the final pass did not cite, so synthesis cannot silently drop them.
                    retained_evidence = set(evidence)
                    omitted = [item for item in answers if not set(item["evidence"]).issubset(retained_evidence)]
                    for item in omitted:
                        if item["answer"] not in answer_text:
                            answer_text += "\n\n" + item["answer"]
                        evidence.extend(source for source in item["evidence"] if source in {m["id"] for m in messages})
                    evidence = list(dict.fromkeys(evidence))
                    if omitted:
                        warnings.append("Some validated chunk answers were retained separately because the final synthesis did not cite them.")
                elif failed_chunks:
                    answer_text = ("\n\n".join(unique_answers[:8]) + "\n\n") if unique_answers else ""
                    answer_text += "The final source review did not return a complete grounded conclusion, and one or more section checks failed. No complete negative conclusion is available."
                    confidence = "low"
                elif unique_answers:
                    answer_text = "\n\n".join(unique_answers[:8])
                    confidence = "low" if any(item["confidence"] == "low" for item in answers) else "medium"
                    warnings.append("The final synthesis did not produce a grounded answer; validated answers from each checked section are shown separately.")
                else:
                    answer_text = f"I checked all {len(chunks)} conversation sections and reviewed the original messages, but couldn't find source evidence answering this question. This doesn't prove there is no related context; try rephrasing or review the cited conversation."
                    confidence = "low"
                if synthesis.get("contextTruncated"):
                    warnings.append("Synthesis source context was shortened; every section was checked, but review the citations for cross-section context.")
            except UserError:
                if unique_answers:
                    answer_text = "\n\n".join(unique_answers[:8])
                    confidence = "low"
                    warnings.append("Final synthesis was incomplete. Validated answers from all checked sections are shown separately.")
                else:
                    answer_text = "I couldn't complete the final source review after checking each section. No conclusion is available yet."
                    confidence = "low"
                    warnings.append("Final synthesis failed, so the question result is incomplete and no negative conclusion is available.")
        elif unique_answers and evidence:
            confidence = "low" if any(item["confidence"] == "low" for item in answers) else (
                "medium" if any(item["confidence"] == "medium" for item in answers) else "high")
            answer_text = sanitize_generated_text("\n\n".join(unique_answers[:8]), user_name)
            if failed_chunks:
                confidence = "low"
        elif failed_chunks:
            answer_text = "I couldn't complete this question across the conversation because one or more sections did not return a grounded result. No conclusion is available yet."
            confidence = "low"
        else:
            answer_text = f"I checked all {len(chunks)} conversation section{'s' if len(chunks) != 1 else ''} and couldn't find a source message that answers this question. This doesn't prove there is no related context; try rephrasing or reviewing the original messages."
            confidence = "low"
        with JOBS_LOCK:
            JOBS[job_id].update({"state": "done", "stage": "complete", "completed": len(chunks) + (1 if len(chunks) > 1 else 0),
                                 "total": len(chunks) + (1 if len(chunks) > 1 else 0), "message": "Answer ready.", "answer": sanitize_generated_text(answer_text, user_name),
                                 "confidence": confidence, "evidence": evidence, "warnings": warnings, "sourceJobId": source_job_id})
    except UserError as exc:
        with JOBS_LOCK:
            JOBS[job_id].update({"state": "error", "stage": "error",
                                 "message": sanitize_generated_text(str(exc), user_name if "user_name" in locals() else "")})
    except Exception as exc:
        with JOBS_LOCK:
            JOBS[job_id].update({"state": "error", "stage": "error",
                                 "message": sanitize_generated_text(f"Question failed: {exc}", user_name if "user_name" in locals() else "")})


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(redact_phone_numbers(f"[{self.log_date_time_string()}] {fmt % args}"))

    def respond(self, status: int, data: dict):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/api/status":
            try:
                validate_local_ollama_url()
                endpoint_error = ""
            except UserError as exc:
                endpoint_error = str(exc)
            models = ollama_tags()
            return self.respond(200, {"ollama": bool(models), "url": OLLAMA_URL,
                                      "models": models, "defaultModel": DEFAULT_MODEL,
                                      "endpointError": endpoint_error,
                                      "quickQuestions": QUICK_QUESTIONS,
                                      "appName": "Unmissed",
                                      "tagline": "Stop scrolling. Start knowing what matters."})
        if self.path.startswith("/api/jobs/"):
            prune_jobs()
            job_id = self.path.rsplit("/", 1)[-1]
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                if job:
                    job = public_job_data(job)
            return self.respond(200 if job else 404, job or {"error": "Analysis job not found."})
        if self.path in ("/", "/index.html"):
            return self.serve_file("index.html", "text/html; charset=utf-8")
        if self.path == "/styles.css":
            return self.serve_file("styles.css", "text/css; charset=utf-8")
        if self.path == "/app.js":
            return self.serve_file("app.js", "text/javascript; charset=utf-8")
        return self.respond(404, {"error": "Not found."})

    def serve_file(self, name: str, mime: str):
        content = (ROOT / name).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        if self.path == "/api/ask":
            return self.start_question()
        if self.path != "/api/analyze":
            return self.respond(404, {"error": "Not found."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                return self.respond(413, {"error": "Request is empty or exceeds the 20 MB upload limit."})
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            raw = data.get("text", "")
            model = str(data.get("model", DEFAULT_MODEL)).strip()
            user_name = str(data.get("userName", "")).strip()[:100]
            if not isinstance(raw, str) or not model:
                return self.respond(400, {"error": "Transcript text and an Ollama model are required."})
            # Parse before starting so format and size issues are reported immediately.
            parse_transcript_with_warnings(raw)
            job_id = uuid.uuid4().hex
            prune_jobs()
            with JOBS_LOCK:
                JOBS[job_id] = {"state": "queued", "stage": "queued", "completed": 0,
                                "total": 0, "message": "Waiting to start…", "_createdAt": time.monotonic()}
            threading.Thread(target=run_job, args=(job_id, raw, model, user_name), daemon=True).start()
            return self.respond(202, {"jobId": job_id})
        except UserError as exc:
            return self.respond(400, {"error": str(exc)})
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return self.respond(400, {"error": f"Couldn't read the request: {exc}"})

    def start_question(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 64 * 1024:
                return self.respond(413, {"error": "Question request is empty or too large."})
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            source_job_id = str(data.get("jobId", ""))
            question = str(data.get("question", "")).strip()
            if not question or len(question) > 1000:
                return self.respond(400, {"error": "Enter a question between 1 and 1,000 characters."})
            prune_jobs()
            with JOBS_LOCK:
                source = JOBS.get(source_job_id)
                if not source or source.get("state") != "done" or not source.get("messages"):
                    return self.respond(404, {"error": "Conversation not found. Import it again before asking."})
                question_job_id = uuid.uuid4().hex
                JOBS[question_job_id] = {"state": "queued", "stage": "queued", "completed": 0,
                                         "total": 0, "message": "Preparing a grounded answer…", "kind": "answer",
                                         "sourceJobId": source_job_id, "_createdAt": time.monotonic()}
            threading.Thread(target=run_question, args=(question_job_id, source_job_id, question), daemon=True).start()
            return self.respond(202, {"jobId": question_job_id})
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return self.respond(400, {"error": f"Couldn't read the question: {exc}"})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Unmissed: http://127.0.0.1:{port}")
    print(f"Ollama endpoint: {OLLAMA_URL} (default model: {DEFAULT_MODEL})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()
