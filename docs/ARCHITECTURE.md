# Architecture

## Layered model

```text
Provider transcript
       │
       ▼
Provider adapter
       │
       ▼
ATIF v1.7 trajectory
       ├────────► ASB `extra.agent_session_bridge` provenance and fidelity
       ├────────► best-effort redaction
       ▼
Target adapter
       ▼
Target payload or target-owned supported importer
```

## Responsibility boundaries

### ATIF: portable trajectory/interchange

ATIF is the external canonical representation. It defines ordered system/user/agent steps, structured tool calls, observations correlated by call ID, agent metadata, optional metrics, and `extra` for extensions. ASB depends on the official `atif` models rather than maintaining a parallel canonical schema.

### Agent Session Bridge: normalization and evidence

ASB parses provider-specific logs, attaches Claude Code's later `tool_result` blocks to the originating agent step as ATIF observations, redacts obvious secrets, records conversion evidence, and maps ATIF into target-specific payloads. Its only project-specific format surface is the `agent_session_bridge` namespace in ATIF's `extra` field.

### Target runtime: native import and resumability

Only the target harness can validate and create native session state. An ATIF document may preserve portable history while a target still lacks an API to ingest it, bind it to a workspace, validate its invariants, and return a resumable native session ID.

## Antigravity boundary

The Antigravity exporter generates a reference mapping to observed derived `transcript.jsonl` records. It deliberately stops before Antigravity's internal SQLite persistence. A supported target-side operation such as `agy import-session --atif trajectory.atif.json` would be required to close the native-resumption boundary.
