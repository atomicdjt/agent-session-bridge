from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, TextIO

from atif import Agent, Observation, ObservationResult, Step, ToolCall, Trajectory

from bridge.models import FidelityReport, asb_extension


def parse_claude_jsonl(file_stream: TextIO) -> Trajectory:
    """Normalize supported Claude Code JSONL records into an ATIF v1.7 trajectory.

    Claude Code places tool results inside later user records. ATIF models those
    results as observations on the agent step that made the corresponding call,
    so the parser moves only the tool-result block while preserving adjacent user
    text as its own ATIF user step.
    """
    steps: list[Step] = []
    tool_call_steps: dict[str, Step] = {}
    session_id: str | None = None
    version = "unknown"
    cwd: str | None = None
    git_branch: str | None = None
    fidelity = FidelityReport()
    normalized_tool_results = False

    for raw_line in file_stream:
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            fidelity.unsupported_source_records += 1
            continue
        if not isinstance(record, dict):
            fidelity.unsupported_source_records += 1
            continue

        record_type = record.get("type")
        if record_type not in {"user", "assistant", "system"}:
            fidelity.unsupported_source_records += 1
            continue

        session_id = session_id or record.get("sessionId")
        if version == "unknown" and record.get("version"):
            version = str(record["version"])
        cwd = cwd or record.get("cwd")
        git_branch = git_branch or record.get("gitBranch")

        message = record.get("message")
        if not isinstance(message, dict):
            fidelity.unsupported_source_records += 1
            continue

        role = message.get("role", record_type)
        if role not in {"user", "assistant", "system"}:
            fidelity.unsupported_source_records += 1
            continue

        timestamp = record.get("timestamp") or None
        content, tool_calls, tool_results = _parse_content_blocks(
            message.get("content", []), role, fidelity
        )

        if role == "assistant":
            step = Step(
                step_id=len(steps) + 1,
                timestamp=timestamp,
                source="agent",
                message=content,
                tool_calls=tool_calls or None,
            )
            steps.append(step)
            for tool_call in tool_calls:
                tool_call_steps[tool_call.tool_call_id] = step
        else:
            _attach_tool_results(tool_results, tool_call_steps, fidelity)
            if content or not tool_results:
                steps.append(
                    Step(
                        step_id=len(steps) + 1,
                        timestamp=timestamp,
                        source=role,
                        message=content,
                    )
                )
            if tool_results:
                normalized_tool_results = True

        fidelity.source_records_preserved += 1

    if normalized_tool_results:
        fidelity.transformations.append(
            "Moved Claude Code tool_result blocks to call-correlated ATIF observations."
        )

    return Trajectory(
        schema_version="ATIF-v1.7",
        session_id=session_id,
        agent=Agent(
            name="claude-code",
            version=version,
            extra={"provider": "anthropic"},
        ),
        steps=steps,
        extra=asb_extension(
            original_format="claude-code-jsonl",
            converted_by="agent-session-bridge",
            conversion_timestamp=datetime.now(UTC).isoformat(),
            fidelity=fidelity,
            workspace=_workspace_metadata(cwd, git_branch),
        ),
    )


def _parse_content_blocks(
    content_blocks: Any, role: str, fidelity: FidelityReport
) -> tuple[str, list[ToolCall], list[ObservationResult]]:
    if isinstance(content_blocks, str):
        return content_blocks, [], []
    if not isinstance(content_blocks, list):
        fidelity.unsupported_source_blocks += 1
        return "", [], []

    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    tool_results: list[ObservationResult] = []
    for block in content_blocks:
        if not isinstance(block, dict):
            fidelity.unsupported_source_blocks += 1
            continue
        block_type = block.get("type")
        if block_type == "text":
            text_parts.append(str(block.get("text", "")))
        elif block_type == "tool_use":
            if role != "assistant":
                fidelity.unsupported_source_blocks += 1
                continue
            call_id = block.get("id")
            arguments = block.get("input", {})
            if (
                not isinstance(call_id, str)
                or not call_id.strip()
                or not isinstance(arguments, dict)
            ):
                fidelity.unsupported_source_blocks += 1
                continue
            tool_calls.append(
                ToolCall(
                    tool_call_id=call_id,
                    function_name=str(block.get("name", "")),
                    arguments=arguments,
                )
            )
            fidelity.tool_calls_preserved += 1
        elif block_type == "tool_result":
            if role != "user":
                fidelity.unsupported_source_blocks += 1
                continue
            result_call_id = block.get("tool_use_id")
            tool_results.append(
                ObservationResult(
                    source_call_id=(
                        result_call_id
                        if isinstance(result_call_id, str) and result_call_id.strip()
                        else None
                    ),
                    content=_tool_result_text(block.get("content", ""), fidelity),
                    extra={"is_error": bool(block.get("is_error"))}
                    if block.get("is_error")
                    else None,
                )
            )
        else:
            fidelity.unsupported_source_blocks += 1
    return "\n".join(part for part in text_parts if part), tool_calls, tool_results


def _tool_result_text(value: Any, fidelity: FidelityReport) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        text_parts: list[str] = []
        for block in value:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
                    continue
            fidelity.unsupported_source_blocks += 1
        return "".join(text_parts)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _attach_tool_results(
    results: list[ObservationResult],
    tool_call_steps: dict[str, Step],
    fidelity: FidelityReport,
) -> None:
    for result in results:
        source_step = (
            tool_call_steps.get(result.source_call_id) if result.source_call_id else None
        )
        if source_step is None:
            fidelity.orphaned_tool_results += 1
            continue
        if source_step.observation is None:
            source_step.observation = Observation(results=[])
        source_step.observation.results.append(result)
        fidelity.observation_results_preserved += 1


def _workspace_metadata(cwd: str | None, git_branch: str | None) -> dict[str, Any] | None:
    if not cwd and not git_branch:
        return None
    workspace: dict[str, Any] = {}
    if cwd:
        workspace["cwd"] = cwd
    if git_branch:
        workspace["repository"] = {"branch": git_branch}
    return workspace
