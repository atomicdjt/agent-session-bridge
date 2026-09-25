"""Allowlist sanitizer and privacy scan for Claude Code session logs.

This is a development tool for preparing a *candidate* public fixture from a private
session. It is not part of the installed package and it does not make anything safe to
publish: the scan is a gate that can only fail a candidate, and a human must still
review every retained string before a fixture is committed.

The sanitizer is structure preserving. Anything not on an allowlist is dropped, but
record types, field names, block types, and identifier relationships survive as
placeholders, so converting the sanitized file produces the same fidelity accounting as
converting the raw one. ``tools/private_demo.py`` checks that claim.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

DROPPED = "[dropped]"
WORKSPACE = "/workspace"
SESSION_PLACEHOLDER = "session-demo"

_CONVERTED_TYPES = frozenset({"user", "assistant", "system"})
_KEEP_TOP_FIELDS = frozenset({"type", "timestamp", "sessionId", "version", "gitBranch", "cwd", "message"})
_KEEP_MESSAGE_FIELDS = frozenset({"role", "content", "model", "id", "usage"})
_USAGE_COUNTS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)


@dataclass
class DropReport:
    """Everything the sanitizer removed, replaced, or kept, as counts."""

    records_reduced_to_skeleton: Counter[str] = field(default_factory=Counter)
    fields_replaced: Counter[str] = field(default_factory=Counter)
    block_parts_removed: Counter[str] = field(default_factory=Counter)
    blocks_reduced_to_skeleton: Counter[str] = field(default_factory=Counter)
    identifiers_pseudonymized: Counter[str] = field(default_factory=Counter)
    path_substitutions: int = 0
    content_retained: Counter[str] = field(default_factory=Counter)

    def as_dict(self) -> dict[str, Any]:
        return {
            "records_reduced_to_type_only_skeleton": dict(sorted(self.records_reduced_to_skeleton.items())),
            "fields_replaced_with_placeholder": dict(sorted(self.fields_replaced.items())),
            "block_parts_removed": dict(sorted(self.block_parts_removed.items())),
            "blocks_reduced_to_type_only_skeleton": dict(sorted(self.blocks_reduced_to_skeleton.items())),
            "identifiers_pseudonymized": dict(sorted(self.identifiers_pseudonymized.items())),
            "path_substitutions": self.path_substitutions,
            "content_retained_verbatim_needs_manual_review": dict(sorted(self.content_retained.items())),
        }


class _Sanitizer:
    def __init__(self, path_variants: list[str]) -> None:
        # Longest first so a more specific variant is never pre-empted by a prefix.
        self._paths = sorted({p for p in path_variants if p}, key=len, reverse=True)
        self._ids: dict[str, dict[str, str]] = {"message": {}, "tool_call": {}}
        self._sessions: set[str] = set()
        self.report = DropReport()

    def _pseudonym(self, kind: str, value: Any) -> Any:
        if not isinstance(value, str) or not value:
            return value
        table = self._ids[kind]
        if value not in table:
            table[value] = f"{kind.replace('_', '-')}-{len(table) + 1:04d}"
            self.report.identifiers_pseudonymized[kind] += 1
        return table[value]

    def _scrub(self, value: Any) -> Any:
        """Apply path substitution to every string in a retained value."""
        if isinstance(value, str):
            for variant in self._paths:
                if variant in value:
                    self.report.path_substitutions += value.count(variant)
                    value = value.replace(variant, WORKSPACE)
            return value
        if isinstance(value, list):
            return [self._scrub(item) for item in value]
        if isinstance(value, dict):
            return {self._scrub(k): self._scrub(v) for k, v in value.items()}
        return value

    def record(self, record: Any) -> dict[str, Any]:
        if not isinstance(record, dict):
            self.report.records_reduced_to_skeleton["(non-object JSON value)"] += 1
            return {"type": "unknown"}
        record_type = record.get("type")
        message = record.get("message")
        if record_type not in _CONVERTED_TYPES or not isinstance(message, dict):
            return self._skeleton(record)
        out: dict[str, Any] = {}
        for key, value in record.items():
            if key not in _KEEP_TOP_FIELDS:
                out[key] = DROPPED
                self.report.fields_replaced[key] += 1
            elif key == "message":
                out[key] = self._message(message)
            elif key == "sessionId":
                out[key] = SESSION_PLACEHOLDER if value else value
                if isinstance(value, str) and value and value not in self._sessions:
                    self._sessions.add(value)
                    self.report.identifiers_pseudonymized["session"] += 1
            elif key == "cwd":
                out[key] = WORKSPACE if isinstance(value, str) and value else value
            else:
                out[key] = self._scrub(value)
        return out

    def _skeleton(self, record: dict[str, Any]) -> dict[str, Any]:
        record_type = record.get("type")
        label = record_type if isinstance(record_type, str) and record_type else "(untyped record)"
        out: dict[str, Any] = {} if record_type is None else {"type": record_type}
        subtype = record.get("subtype")
        if record_type == "system" and isinstance(subtype, str):
            out["subtype"] = subtype
            label = f"system/{subtype}"
        self.report.records_reduced_to_skeleton[label] += 1
        return out

    def _message(self, message: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in message.items():
            if key not in _KEEP_MESSAGE_FIELDS:
                out[key] = DROPPED
                self.report.fields_replaced[f"message.{key}"] += 1
            elif key == "content":
                out[key] = self._content(value)
            elif key == "id":
                out[key] = self._pseudonym("message", value)
            elif key == "usage":
                out[key] = self._usage(value)
            else:
                out[key] = self._scrub(value)
        return out

    def _usage(self, usage: Any) -> Any:
        if not isinstance(usage, dict):
            self.report.fields_replaced["message.usage (not an object)"] += 1
            return DROPPED
        kept = {k: usage[k] for k in _USAGE_COUNTS if k in usage}
        removed = len(usage) - len(kept)
        if removed:
            self.report.block_parts_removed["usage.<other fields>"] += removed
        return kept

    def _content(self, content: Any) -> Any:
        if isinstance(content, str):
            self.report.content_retained["message content string"] += 1
            return self._scrub(content)
        if not isinstance(content, list):
            self.report.fields_replaced["message.content (unexpected type)"] += 1
            return DROPPED
        return [self._block(block) for block in content]

    def _block(self, block: Any) -> Any:
        if not isinstance(block, dict):
            self.report.blocks_reduced_to_skeleton["(non-object block)"] += 1
            return DROPPED
        block_type = block.get("type")
        if block_type == "text" and isinstance(block.get("text"), str):
            self.report.content_retained["text block"] += 1
            return {"type": "text", "text": self._scrub(block["text"])}
        if block_type == "tool_use":
            self.report.content_retained["tool_use name and input"] += 1
            self._count_removed(block, {"type", "id", "name", "input"}, "tool_use")
            return {
                "type": "tool_use",
                "id": self._pseudonym("tool_call", block.get("id")),
                "name": self._scrub(block.get("name")),
                "input": self._scrub(block.get("input", {})),
            }
        if block_type == "tool_result":
            self.report.content_retained["tool_result content"] += 1
            self._count_removed(block, {"type", "tool_use_id", "content", "is_error"}, "tool_result")
            out: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": self._pseudonym("tool_call", block.get("tool_use_id")),
                "content": self._result_content(block.get("content", "")),
            }
            if "is_error" in block:
                out["is_error"] = block["is_error"]
            return out
        if block_type == "thinking":
            text = block.get("thinking")
            self._count_removed(block, {"type", "thinking"}, "thinking")
            # Keep only whether the block held text, which is what the fidelity report uses.
            if isinstance(text, str) and text.strip():
                self.report.blocks_reduced_to_skeleton["thinking (text replaced)"] += 1
                return {"type": "thinking", "thinking": DROPPED}
            return {"type": "thinking", "thinking": ""}
        label = block_type if isinstance(block_type, str) and block_type else "(untyped block)"
        self.report.blocks_reduced_to_skeleton[label] += 1
        return {"type": block_type} if block_type is not None else {}

    def _result_content(self, content: Any) -> Any:
        if isinstance(content, str):
            return self._scrub(content)
        if isinstance(content, list):
            items: list[Any] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                    items.append({"type": "text", "text": self._scrub(item["text"])})
                elif isinstance(item, dict) and item.get("type") == "image":
                    self.report.blocks_reduced_to_skeleton["tool_result image"] += 1
                    items.append({"type": "image", "source": {"data": DROPPED}})
                else:
                    self.report.blocks_reduced_to_skeleton["tool_result item"] += 1
                    items.append({"type": item.get("type") if isinstance(item, dict) else None})
            return items
        return self._scrub(content)

    def _count_removed(self, block: dict[str, Any], keep: set[str], label: str) -> None:
        for key in block:
            if key not in keep:
                self.report.block_parts_removed[f"{label}.{key}"] += 1


def sanitize_records(
    records: list[Any], *, path_variants: list[str]
) -> tuple[list[dict[str, Any]], DropReport]:
    """Return sanitized records and a report of everything that was dropped or kept."""
    sanitizer = _Sanitizer(path_variants)
    return [sanitizer.record(record) for record in records], sanitizer.report


def path_variants_for(cwd: str) -> list[str]:
    """The spellings of a working directory a Windows session can leave in tool text."""
    if not cwd:
        return []
    backslash = cwd.replace("/", "\\")
    forward = cwd.replace("\\", "/")
    variants = [backslash, forward]
    match = re.match(r"^([A-Za-z]):[\\/](.*)$", cwd)
    if match:
        rest = match.group(2).replace("\\", "/")
        variants += [f"/{match.group(1).lower()}/{rest}", f"/mnt/{match.group(1).lower()}/{rest}"]
    return variants


# --- privacy scan ---------------------------------------------------------------------

_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_URL = re.compile(r"\bhttps?://[^\s\"'<>)]+", re.IGNORECASE)
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_LONG_TOKEN = re.compile(r"[A-Za-z0-9_\-+/=]{32,}")
_ABS_PATH = re.compile(r"(?:\b[A-Za-z]:[\\/]|(?<![\w.:])/(?:home|Users|usr|var|etc|tmp|mnt|c|d)/)[^\s\"'<>]*")


@dataclass
class Finding:
    severity: str  # "FAIL" blocks the candidate; "REVIEW" needs a human look
    category: str
    location: str
    excerpt: str

    def as_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "category": self.category,
            "location": self.location,
            "excerpt": self.excerpt,
        }


def _mask(text: str) -> str:
    """Enough to find a hit, not enough to reproduce a secret."""
    return text if len(text) <= 3 else f"{text[:2]}…({len(text)} chars)"


def _strings(value: Any, location: str) -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(location, value)]
    if isinstance(value, list):
        return [pair for i, item in enumerate(value) for pair in _strings(item, f"{location}[{i}]")]
    if isinstance(value, dict):
        pairs: list[tuple[str, str]] = []
        for key, item in value.items():
            pairs.append((f"{location}.<key>", str(key)))
            pairs += _strings(item, f"{location}.{key}")
        return pairs
    return []


def scan_text(location: str, text: str, terms: list[str], redactor: Any) -> list[Finding]:
    findings: list[Finding] = []
    lowered = text.lower().replace("\\", "/")
    for term in terms:
        needle = term.lower().replace("\\", "/")
        if needle and needle in lowered:
            findings.append(Finding("FAIL", "forbidden_term", location, f"term #{terms.index(term) + 1}"))
    for category, pattern in (("uuid", _UUID), ("email", _EMAIL)):
        for match in pattern.finditer(text):
            findings.append(Finding("FAIL", category, location, _mask(match.group(0))))
    if redactor(text) != text:
        findings.append(Finding("FAIL", "secret_shape (ASB redactor would change this text)", location, "text"))
    for category, pattern in (("url", _URL), ("ip_address", _IPV4), ("long_token_like_run", _LONG_TOKEN)):
        for match in pattern.finditer(text):
            findings.append(Finding("REVIEW", category, location, _mask(match.group(0))))
    for match in _ABS_PATH.finditer(text):
        if not match.group(0).startswith(WORKSPACE):
            findings.append(Finding("REVIEW", "absolute_path", location, _mask(match.group(0))))
    return findings


def scan_records(records: list[Any], terms: list[str], redactor: Any) -> list[Finding]:
    findings: list[Finding] = []
    for index, record in enumerate(records, start=1):
        for location, text in _strings(record, f"line {index}"):
            findings += scan_text(location, text, terms, redactor)
    return findings


def summarize(findings: list[Finding]) -> dict[str, Any]:
    failures = [f for f in findings if f.severity == "FAIL"]
    return {
        "status": "FAIL" if failures else "PASS",
        "fail_count": len(failures),
        "review_count": len(findings) - len(failures),
        "meaning": (
            "PASS only means the automatic checks found nothing. It is not a clearance: "
            "every retained string still needs manual review before publication."
        ),
        "findings": [f.as_dict() for f in findings],
    }


def dumps_jsonl(records: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
