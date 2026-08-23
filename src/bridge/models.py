from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FidelityReport(BaseModel):
    """ASB transformation accounting, not a replacement interchange schema."""

    source_records_preserved: int = 0
    tool_calls_preserved: int = 0
    observation_results_preserved: int = 0
    unsupported_source_records: int = 0
    unsupported_source_blocks: int = 0
    orphaned_tool_results: int = 0
    transformations: list[str] = Field(default_factory=list)


def asb_extension(
    *,
    original_format: str,
    converted_by: str,
    conversion_timestamp: str,
    fidelity: FidelityReport,
    workspace: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return the namespaced ATIF ``extra`` payload owned by this project."""
    bridge: dict[str, Any] = {
        "provenance": {
            "original_format": original_format,
            "converted_by": converted_by,
            "conversion_timestamp": conversion_timestamp,
        },
        "fidelity": fidelity.model_dump(),
    }
    if workspace:
        bridge["workspace"] = workspace
    return {"agent_session_bridge": bridge}
