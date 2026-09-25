from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RecordTypeLoss(BaseModel):
    """Source records of one type that were not converted, with an evidence-based category."""

    type: str
    category: str
    records: int


class BlockTypeLoss(BaseModel):
    """Content blocks of one type that were not converted."""

    type: str
    blocks: int
    with_content: int


class IgnoredField(BaseModel):
    """A field on converted source records that ATIF has no place for and ASB did not carry."""

    field: str
    records: int


class FidelityReport(BaseModel):
    """ASB transformation accounting, not a replacement interchange schema."""

    source_records_preserved: int = 0
    tool_calls_preserved: int = 0
    observation_results_preserved: int = 0
    unsupported_source_records: int = 0
    unsupported_source_blocks: int = 0
    orphaned_tool_results: int = 0
    omitted_tool_result_timestamps: int = 0
    invalid_source_timestamps: int = 0
    unsupported_record_types: list[RecordTypeLoss] = Field(default_factory=list)
    unsupported_block_types: list[BlockTypeLoss] = Field(default_factory=list)
    ignored_fields: list[IgnoredField] = Field(default_factory=list)
    synthetic_agent_records: int = 0
    duplicate_usage_records: int = 0
    conflicting_usage_records: int = 0
    transformations: list[str] = Field(default_factory=list)

    def count_unsupported_record(self, label: str, category: str) -> None:
        """Count one source record that was not converted, by type and category."""
        self.unsupported_source_records += 1
        for entry in self.unsupported_record_types:
            if entry.type == label and entry.category == category:
                entry.records += 1
                return
        self.unsupported_record_types.append(
            RecordTypeLoss(type=label, category=category, records=1)
        )

    def count_unsupported_block(self, label: str, *, with_content: bool) -> None:
        """Count one content block that was not converted, by type."""
        self.unsupported_source_blocks += 1
        for entry in self.unsupported_block_types:
            if entry.type == label:
                entry.blocks += 1
                entry.with_content += int(with_content)
                return
        self.unsupported_block_types.append(
            BlockTypeLoss(type=label, blocks=1, with_content=int(with_content))
        )

    def count_ignored_field(self, field: str) -> None:
        """Count one converted source record that carried a field ASB did not convert."""
        for entry in self.ignored_fields:
            if entry.field == field:
                entry.records += 1
                return
        self.ignored_fields.append(IgnoredField(field=field, records=1))

    def sort_breakdowns(self) -> None:
        """Order breakdown lists by name so the serialized report is deterministic."""
        self.unsupported_record_types.sort(key=lambda entry: (entry.type, entry.category))
        self.unsupported_block_types.sort(key=lambda entry: entry.type)
        self.ignored_fields.sort(key=lambda entry: entry.field)


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
