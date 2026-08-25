from __future__ import annotations

import re
from typing import Any

from atif import ContentPart, Trajectory

SECRET_PATTERNS = [
    (
        re.compile(
            r'(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|password)\s*[:=]\s*["\'][a-zA-Z0-9_\-\.]{10,}["\']'
        ),
        r'\1 = "[REDACTED]"',
    ),
    (
        re.compile(
            r'(?i)\b(api[_-]?key|secret[_-]?key|access[_-]?token|password|token)'
            r'\s*[:=]\s*[a-zA-Z0-9][a-zA-Z0-9_./+=-]{9,}'
        ),
        r'\1 = "[REDACTED]"',
    ),
    (
        re.compile(r'(?i)\b(Bearer)\s+[a-zA-Z0-9._~+/=-]{10,}'),
        r'\1 [REDACTED]',
    ),
    (
        re.compile(r'(?i)\b(?:gh[pousr]_|github_pat_)[a-zA-Z0-9_]{10,}'),
        "[REDACTED]",
    ),
    (re.compile(r'\bsk-[a-zA-Z0-9_-]{10,}'), "[REDACTED]"),
    (re.compile(r"xox[baprs]-[0-9a-zA-Z]{10,}"), "xox?-***REDACTED***"),
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
        return {key: _redact_value(item) for key, item in value.items()}
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
