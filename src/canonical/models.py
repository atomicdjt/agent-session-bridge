from __future__ import annotations
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ProviderInfo(BaseModel):
    provider: str
    agent: str
    version: str | None = None

class RepoMetadata(BaseModel):
    repository_url: str | None = None
    branch: str | None = None
    commit_hash: str | None = None
    dirty: bool | None = None

class Workspace(BaseModel):
    cwd: str
    repository: RepoMetadata | None = None

class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class Artifact(BaseModel):
    id: str
    path: str | None = None
    content: str | None = None
    is_truncated: bool = False

class ToolInvocation(BaseModel):
    tool_id: str
    name: str
    arguments: dict[str, Any]

class ToolResult(BaseModel):
    tool_id: str
    status: str
    output: str | None = None

class Turn(BaseModel):
    turn_id: str
    role: MessageRole
    timestamp: str
    content: str
    tool_invocations: list[ToolInvocation] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

class ExecutionMetadata(BaseModel):
    token_usage: dict[str, int] = Field(default_factory=dict)
    duration_ms: int | None = None

class LossReport(BaseModel):
    turns_preserved: int = 0
    turns_omitted: int = 0
    tools_preserved: int = 0
    tools_omitted: int = 0
    unsupported_events: int = 0
    synthesized_records: int = 0
    details: list[str] = Field(default_factory=list)

class Provenance(BaseModel):
    original_format: str
    conversion_timestamp: str
    converted_by: str
    loss_report: LossReport

class ASEFSession(BaseModel):
    schema_version: str = "1.0"
    session_id: str
    source: ProviderInfo
    workspace: Workspace
    turns: list[Turn]
    artifacts: list[Artifact] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    unresolved_work: list[str] = Field(default_factory=list)
    execution_metadata: ExecutionMetadata = Field(default_factory=ExecutionMetadata)
    provenance: Provenance
    extensions: dict[str, Any] = Field(default_factory=dict)
