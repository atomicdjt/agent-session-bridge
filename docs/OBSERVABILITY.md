# Observability Integration

Agent Session Bridge provides an optional observability projection that converts an Agent Trajectory Interchange Format (ATIF) session into OpenTelemetry (OTel) spans following OpenInference GenAI semantic conventions. This allows viewing offline agent trajectories in tools like Arize Phoenix.

## Core Design Principle
**ATIF is the source of truth.** The observability projection is a one-way mapping *from* ATIF *to* OpenTelemetry. It does not replace ATIF as the portable trajectory format.

## Semantic Mapping Matrix

| ASB / ATIF concept | OpenTelemetry GenAI / OpenInference Representation | Confidence | Loss / Caveat |
| ------------------ | -------------------------------------------------- | ---------- | ------------- |
| source `session_id` | `session.id` | High | Emitted only when a genuine source session ID exists; no substitute is generated. |
| Agent Step (`source`) | `Span` (Kind: `AGENT`) | Medium | Grouped logically per step source. |
| step `source` | `agent_session_bridge.step_source` | High | ASB namespace; not an OpenInference message array. |
| `message` | `input.value` / `output.value` | High | Present only in explicit content modes. |
| `tool_calls` | `Span` (Kind: `TOOL`), `tool.name`, `tool.id` | High | Tool calls are mapped with `tool_call_id`. |
| `observation.results` | TOOL `output.value` | High | Present only in explicit content modes. Correlated via `source_call_id`. |
| timestamps | Span points/boundaries | High | Step timestamps are source-observed points; tool execution duration is zero as observations do not have independent timestamps. |

## Trace Topology
The ATIF trajectory is mapped as one **historical projection** trace: a root `CHAIN` span contains one `AGENT` span per recorded step and its correlated `TOOL` spans. This is a structural representation of recorded observations, not a claim that ASB observed the original in-process runtime trace.

## Privacy & Content Capture
Coding-agent transcripts contain sensitive information. The projection supports multiple privacy modes:
- `metadata-only` (default): Only structure, roles, and tool names are exported. No text content or tool arguments are exported.
- `redacted-content`: Redacts known secrets on a copy before exporting.
- `full-content`: Exports all content. **Warning:** this can export source code, secrets, commands, file paths, proprietary information, and personal information.

## Fidelity Analysis
- **Preserved:** Tool invocation sequence, conversation roles, chronological order.
- **Transformed:** Timestamps (converted to synthesized spans).
- **Omitted:** Some low-level execution metadata if it lacks OTel standard representation.
- **Unsupported:** Granular token usage per step if only available as an aggregate.
