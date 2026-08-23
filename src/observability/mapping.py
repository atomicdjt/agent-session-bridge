from __future__ import annotations

import json
from typing import Any

from atif import ContentPart, Step, ToolCall, Trajectory

from security.redact import _redact_text as redact_text


def _real_session_id(session_id: str | None) -> bool:
    return bool(session_id and session_id != "unknown")


def project_text(content: str | list[ContentPart]) -> str:
    if isinstance(content, str):
        return content
    return "".join(part.text for part in content if part.type == "text" and part.text)


def _content(value: str | list[ContentPart], privacy_mode: str) -> str:
    text_val = project_text(value)
    return redact_text(text_val) if privacy_mode == "redacted-content" else text_val


def get_openinference_span_attributes(
    trajectory: Trajectory, step: Step, privacy_mode: str = "metadata-only"
) -> dict[str, Any]:
    attributes: dict[str, Any] = {}

    # Session identity
    if _real_session_id(trajectory.session_id):
        attributes["session.id"] = trajectory.session_id

    attributes["openinference.span.kind"] = "AGENT"

    # Message role
    attributes["agent_session_bridge.step_source"] = step.source

    # Message content based on privacy mode
    if privacy_mode in ("full-content", "redacted-content") and step.message:
        attributes["input.value"] = _content(step.message, privacy_mode)
        attributes["input.mime_type"] = "text/plain"

    # ASB specific namespace
    attributes["agent_session_bridge.step_id"] = step.step_id

    # Provider and agent info
    if trajectory.extra and "provider" in trajectory.extra:
        attributes["agent_session_bridge.provider"] = trajectory.extra["provider"]
    elif trajectory.agent and trajectory.agent.extra and "provider" in trajectory.agent.extra:
        attributes["agent_session_bridge.provider"] = trajectory.agent.extra["provider"]

    if trajectory.agent and trajectory.agent.name:
        attributes["agent_session_bridge.agent"] = trajectory.agent.name

    return attributes


def get_tool_span_attributes(
    tool_call: ToolCall, session_id: str | None, privacy_mode: str = "metadata-only"
) -> dict[str, Any]:
    attributes: dict[str, Any] = {}

    if _real_session_id(session_id):
        attributes["session.id"] = session_id

    attributes["openinference.span.kind"] = "TOOL"
    attributes["tool.name"] = tool_call.function_name
    attributes["tool.id"] = tool_call.tool_call_id
    attributes["agent_session_bridge.tool_id"] = tool_call.tool_call_id

    if privacy_mode in ("full-content", "redacted-content") and tool_call.arguments:
        args = tool_call.arguments
        if privacy_mode == "redacted-content":
            from security.redact import _redact_value
            args = _redact_value(args)
        try:
            attributes["input.value"] = json.dumps(args)
        except (TypeError, ValueError):
            attributes["input.value"] = str(args)
        attributes["input.mime_type"] = "application/json"

    return attributes
