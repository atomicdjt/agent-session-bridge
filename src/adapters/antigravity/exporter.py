import json
from dataclasses import dataclass

from atif import ContentPart, Step, Trajectory


@dataclass(frozen=True)
class AntigravityExport:
    payload: str
    omitted_system_messages: int
    omitted_content_parts: int = 0


def export_to_antigravity(trajectory: Trajectory) -> str:
    """Return the reference payload for callers that need only JSONL."""
    return export_with_report(trajectory).payload


def export_with_report(trajectory: Trajectory) -> AntigravityExport:
    """Map an ATIF trajectory to the observed Antigravity derived-log shape.

    This is a reference export only. The generated log is not represented as a
    supported native Antigravity session-import format.
    """
    transcript_lines: list[str] = []
    omitted_system_messages = 0
    omitted_content_parts = 0

    for step in trajectory.steps:
        if step.source == "user":
            text, omitted = _extract_text_and_omissions(step.message)
            omitted_content_parts += omitted
            transcript_lines.append(
                json.dumps(
                    {
                        "step_index": len(transcript_lines) + 1,
                        "source": "USER_EXPLICIT",
                        "type": "USER_INPUT",
                        "status": "DONE",
                        "created_at": step.timestamp,
                        "content": text,
                    }
                )
            )
        elif step.source == "agent":
            text, omitted = _extract_text_and_omissions(step.message)
            omitted_content_parts += omitted
            transcript_lines.append(
                json.dumps(
                    {
                        "step_index": len(transcript_lines) + 1,
                        "source": "MODEL",
                        "type": "PLANNER_RESPONSE",
                        "status": "DONE",
                        "created_at": step.timestamp,
                        "content": text,
                        "tool_calls": _tool_calls(step),
                    }
                )
            )
        elif step.source == "system":
            omitted_system_messages += 1

        if step.observation:
            for result in step.observation.results:
                text, omitted = _extract_text_and_omissions(result.content)
                omitted_content_parts += omitted
                transcript_lines.append(
                    json.dumps(
                        {
                            "step_index": len(transcript_lines) + 1,
                            "source": "SYSTEM",
                            "type": "TOOL_RESPONSE",
                            "status": "DONE",
                            "created_at": step.timestamp,
                            "content": text,
                        }
                    )
                )

    return AntigravityExport(
        payload="\n".join(transcript_lines) + "\n",
        omitted_system_messages=omitted_system_messages,
        omitted_content_parts=omitted_content_parts,
    )


def _extract_text_and_omissions(
    content: str | list[ContentPart] | None,
) -> tuple[str, int]:
    if content is None:
        return "", 0
    if isinstance(content, str):
        return content, 0
    text_parts: list[str] = []
    omitted = 0
    for part in content:
        if part.type == "text" and part.text:
            text_parts.append(part.text)
        else:
            omitted += 1
    return "".join(text_parts), omitted


def _tool_calls(step: Step) -> list[dict[str, object]]:
    return [
        {"name": call.function_name, "args": call.arguments}
        for call in step.tool_calls or []
    ]
