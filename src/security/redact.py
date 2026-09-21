from __future__ import annotations

import re
from typing import Any

from atif import ContentPart, Trajectory

_SEP = r"[_.\-]?"
# Credential-bearing name endings. A name is matched when it *ends* with one of
# these (``OPENAI_API_KEY``, ``client_secret``), so ``credential_type``,
# ``max_tokens`` and ``tokenizer`` stay visible. ``\b`` cannot be used here
# because ``_`` is a word character.
_KEY_TERMS = (
    rf"api{_SEP}key|access{_SEP}key|secret{_SEP}key|private{_SEP}key"
    r"|secret|token|password|passwd|credentials?"
)
# A bounded lazy prefix plus a start lookbehind keeps matching linear on long words.
_KEY = rf"(?<![\w.\-])[\w.\-]{{0,40}}?(?:{_KEY_TERMS})"
_JSON_KEY = rf"(?:{_KEY}|authorization|bearer)"

SENSITIVE_KEY_PATTERN = re.compile(rf"(?i)(?:{_KEY_TERMS}|authorization|bearer|cookie)$")

# Characters that end an unquoted value in shell, URL, and JSON-ish text. The
# backslash is excluded so a JSON-escaped closing quote (\") is left intact.
_STOP = r"\s\"'\\`;&|<>(){}\[\],"
_UNQUOTED_VALUE = rf"[^{_STOP}$][^{_STOP}]{{9,}}"
_HEADER_VALUE = r"[^\s\"'\\]{8,}"

SECRET_PATTERNS = [
    # Private key blocks; an unterminated block is redacted to the end of the text.
    (
        re.compile(
            r"(?s)-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----"
            r".*?(?:-----END [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----|\Z)"
        ),
        "[REDACTED]",
    ),
    # JSON/dict-style pairs: "api_key": "value"
    (
        re.compile(rf'(?i)(["\'])({_JSON_KEY})\1(\s*:\s*)["\'][^"\']{{8,}}["\']'),
        r'\1\2\1\3"[REDACTED]"',
    ),
    # The same pair after one level of JSON string escaping: \"api_key\": \"value\"
    (
        re.compile(rf'(?i)(\\")({_JSON_KEY})\\"(\s*:\s*)\\"[^"\\]{{8,}}\\"'),
        r'\1\2\\"\3\\"[REDACTED]\\"',
    ),
    # KEY=value / KEY: value with a quoted or bare value.
    (
        re.compile(rf'(?i)({_KEY})\s*[:=]\s*["\'][^"\'\s]{{10,}}["\']'),
        r'\1 = "[REDACTED]"',
    ),
    (
        re.compile(rf"(?i)({_KEY})\s*[:=]\s*{_UNQUOTED_VALUE}"),
        r'\1 = "[REDACTED]"',
    ),
    # HTTP credential headers; any auth scheme (Bearer, Basic, token, ...).
    (
        re.compile(rf"(?i)\b(authorization\s*:\s*(?:[a-z][a-z0-9_-]*\s+)?){_HEADER_VALUE}"),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"(?i)\b((?:set-)?cookie\s*:\s*)[^\"'\\\r\n]{8,}"),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"(?i)\b(Bearer)\s+[a-zA-Z0-9._~+/=-]{10,}"),
        r"\1 [REDACTED]",
    ),
    # CLI flags whose value is a separate argument: --token VALUE, --api-key "VALUE"
    (
        re.compile(
            r"(?i)(?<![\w-])(--(?:[a-z0-9]+-)*"
            r"(?:api-?key|access-?key|secret-?key|private-?key|secret|token|password|passwd|credentials?)"
            r"\s+)(?:([\"'])[^\"'\\\r\n]{8,}\2|(?![-$\"'])[^\s\"'\\]{8,})"
        ),
        r"\1[REDACTED]",
    ),
    # Credentials embedded in a URL (scheme://user:secret@host) or `curl -u user:secret`.
    (
        re.compile(r"(://[^\s/:@\"'<>]+:)[^\s/@\"'<>]{3,}(@)"),
        r"\1[REDACTED]\2",
    ),
    (
        re.compile(
            r"(?i)(\bcurl\b[^\r\n]{0,200}?\s(?:-u|--user)(?:\s+|=)[\"']?[^\s:\"']+:)[^\s\"'\\]+"
        ),
        r"\1[REDACTED]",
    ),
    # Well-known credential shapes.
    (
        re.compile(r"(?i)\b(?:gh[pousr]_|github_pat_)[a-zA-Z0-9_]{10,}"),
        "[REDACTED]",
    ),
    (re.compile(r"\bsk-[a-zA-Z0-9_-]{10,}"), "[REDACTED]"),
    (re.compile(r"xox[baprs]-[0-9a-zA-Z]{10,}"), "xox?-***REDACTED***"),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "[REDACTED]"),
    (re.compile(r"\beyJ[\w-]{5,}\.[\w-]{5,}\.[\w-]{5,}"), "[REDACTED]"),
]


def redact_trajectory(trajectory: Trajectory) -> Trajectory:
    """Apply best-effort redaction without changing the ATIF document shape."""
    for step in trajectory.steps:
        step.message = _redact_content(step.message)
        for tool_call in step.tool_calls or []:
            tool_call.arguments = _redact_value(tool_call.arguments)
        if step.observation:
            for result in step.observation.results:
                result.content = _redact_optional_content(result.content)
    trajectory.extra = _redact_extra(trajectory.extra)
    return trajectory


def redact_session(trajectory: Trajectory) -> Trajectory:
    """Compatibility alias for the pre-ATIF helper name."""
    return redact_trajectory(trajectory)


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and SENSITIVE_KEY_PATTERN.search(key):
                if isinstance(item, (dict, list)):
                    result[key] = _redact_value(item)
                elif item is None or isinstance(item, bool):
                    result[key] = item
                else:
                    result[key] = "[REDACTED]"
            else:
                result[key] = _redact_value(item)
        return result
    return value


def _redact_content(value: str | list[ContentPart]) -> str | list[ContentPart]:
    if isinstance(value, str):
        return _redact_text(value)
    return [ContentPart.model_validate(_redact_value(part.model_dump())) for part in value]


def _redact_optional_content(
    value: str | list[ContentPart] | None,
) -> str | list[ContentPart] | None:
    if value is None:
        return None
    return _redact_content(value)


def _redact_extra(extra: dict[str, Any] | None) -> dict[str, Any] | None:
    redacted = _redact_value(extra)
    if not isinstance(redacted, dict):
        return redacted
    bridge = redacted.get("agent_session_bridge")
    if not isinstance(bridge, dict):
        return redacted
    workspace = bridge.get("workspace")
    if not isinstance(workspace, dict):
        return redacted
    workspace.pop("cwd", None)
    if not workspace:
        bridge.pop("workspace", None)
    return redacted


def _redact_text(value: str) -> str:
    for pattern, replacement in SECRET_PATTERNS:
        value = pattern.sub(replacement, value)
    return value
