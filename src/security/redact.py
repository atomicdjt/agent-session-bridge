from __future__ import annotations

import re
from typing import Any

from atif import Trajectory

SECRET_PATTERNS = [
    (
        re.compile(
            r'(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|password)\s*[:=]\s*["\'][a-zA-Z0-9_\-\.]{10,}["\']'
        ),
        r'\1 = "[REDACTED]"',
    ),
    (re.compile(r"xox[baprs]-[0-9a-zA-Z]{10,}"), "xox?-***REDACTED***"),
]


def redact_trajectory(trajectory: Trajectory) -> Trajectory:
    """Apply best-effort redaction without changing the ATIF document shape."""
    for step in trajectory.steps:
        if isinstance(step.message, str):
            step.message = _redact_text(step.message)
        for tool_call in step.tool_calls or []:
            tool_call.arguments = _redact_value(tool_call.arguments)
        if step.observation:
            for result in step.observation.results:
                if isinstance(result.content, str):
                    result.content = _redact_text(result.content)
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


def _redact_text(value: str) -> str:
    for pattern, replacement in SECRET_PATTERNS:
        value = pattern.sub(replacement, value)
    return value
