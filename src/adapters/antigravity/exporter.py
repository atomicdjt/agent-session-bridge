import json
from dataclasses import dataclass

from atif import Step, Trajectory


@dataclass(frozen=True)
class AntigravityExport:
    payload: str
    omitted_system_messages: int


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

    for step in trajectory.steps:
        if step.source == "user":
            transcript_lines.append(
                json.dumps(
                    {
                        "step_index": len(transcript_lines) + 1,
                        "source": "USER_EXPLICIT",
                        "type": "USER_INPUT",
                        "status": "DONE",
                        "created_at": step.timestamp,
                        "content": step.message,
                    }
                )
            )
        elif step.source == "agent":
            transcript_lines.append(
                json.dumps(
                    {
                        "step_index": len(transcript_lines) + 1,
                        "source": "MODEL",
                        "type": "PLANNER_RESPONSE",
                        "status": "DONE",
                        "created_at": step.timestamp,
                        "content": step.message,
                        "tool_calls": _tool_calls(step),
                    }
                )
            )
        elif step.source == "system" and step.message:
            omitted_system_messages += 1

        if step.observation:
            for result in step.observation.results:
                transcript_lines.append(
                    json.dumps(
                        {
                            "step_index": len(transcript_lines) + 1,
                            "source": "SYSTEM",
                            "type": "TOOL_RESPONSE",
                            "status": "DONE",
                            "created_at": step.timestamp,
                            "content": result.content or "",
                        }
                    )
                )

    return AntigravityExport(
        payload="\n".join(transcript_lines) + "\n",
        omitted_system_messages=omitted_system_messages,
    )


def _tool_calls(step: Step) -> list[dict[str, object]]:
    return [
        {"name": call.function_name, "args": call.arguments}
        for call in step.tool_calls or []
    ]
