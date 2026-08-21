# Agent Session Exchange Format (ASEF)

ASEF is a provider-neutral, versioned JSON schema designed for high-fidelity transfer of developer agent sessions.

## Core Principles
- **Loss Accounting:** Transformations track missing/unsupported fields to avoid silent fidelity degradation.
- **Provider Neutral:** Does not expose any single agent's proprietary internal concepts.
- **Deterministic:** Identical session inputs produce identical ASEF graphs.
- **Structural Identity:** Treats workspace details, tool use, and tool results as first-class schemas, not raw text.

## Schema Version 1.0

### `ASEFSession`
- `schema_version`: "1.0"
- `session_id`: String UUID
- `source`: `ProviderInfo` (e.g. Claude Code version)
- `workspace`: `Workspace` (CWD, repository, branch, etc)
- `turns`: Array of `Turn`
- `artifacts`: Array of `Artifact` (Explicitly separated from turns to avoid huge inline text blocks)
- `provenance`: `Provenance` (Loss reports and conversion records)

### `Turn`
- `turn_id`: String UUID
- `role`: "user" | "assistant" | "system"
- `timestamp`: ISO-8601
- `content`: Text content
- `tool_invocations`: Array of `ToolInvocation`
- `tool_results`: Array of `ToolResult`
