# ATIF Interchange and ASB Extension Profile

Agent Session Bridge emits a valid [ATIF v1.7](https://github.com/harbor-framework/harbor/blob/main/rfcs/0001-trajectory-format.md) `Trajectory` as its portable output. This document records the exact mapping and labels the parts that remain ASB-specific.

## ASEF migration map

| Former ASEF concept | ATIF v1.7 representation | Transform or limitation |
| --- | --- | --- |
| `ASEFSession.schema_version` | `Trajectory.schema_version = "ATIF-v1.7"` | Replaced; ASEF version is not carried forward |
| `session_id` | `Trajectory.session_id` | Preserved when the source supplies it |
| `source.agent` / `source.version` | `Trajectory.agent.name` / `agent.version` | Preserved as `claude-code` and its source version |
| `source.provider` | `Trajectory.agent.extra.provider` | ATIF extension; no custom ASB schema. For Claude Code JSONL the value `anthropic` is inferred from the source format, not observed per record. ATIF v1.7 does not distinguish model vendor, agent harness, and execution host, so `agent.name` (`claude-code`) names the harness and `provenance.original_format` names the source encoding. |
| `Turn` role, time, text | `Step.source`, `timestamp`, `message` | Preserved for supported records. A step timestamp is the timestamp of that step's own source record; see [Timestamp semantics](#timestamp-semantics). |
| `ToolInvocation` | agent-step `tool_calls` | Preserved with ID, name, and JSON arguments |
| `ToolResult` | originating agent-step `observation.results` | Normalized from Claude's later user block; correlated by `source_call_id`. The result's own source timestamp cannot be represented (see below). |
| `Workspace` / repository metadata | `extra.agent_session_bridge.workspace` | ATIF has no portable workspace contract; source-derived metadata only. `redact_trajectory` omits `workspace.cwd` from redacted output. |
| `Provenance` / `LossReport` | `extra.agent_session_bridge.provenance` / `.fidelity` | ASB extension, never represented as ATIF core fields |
| `ExecutionMetadata` | ATIF `metrics` / `final_metrics` when source data supports them | Current Claude adapter does not populate source metrics |
| `Artifact`, `decisions`, `unresolved_work` | No direct current mapping | The v0.1 parser never populated them; no compatibility claim is made |

## ASB extension contract

ASB owns exactly one root extension namespace:

```json
{
  "extra": {
    "agent_session_bridge": {
      "provenance": {
        "original_format": "claude-code-jsonl",
        "converted_by": "agent-session-bridge",
        "conversion_timestamp": "2026-08-22T00:00:00+00:00"
      },
      "fidelity": {
        "source_records_preserved": 4,
        "tool_calls_preserved": 1,
        "observation_results_preserved": 1,
        "unsupported_source_records": 0,
        "unsupported_source_blocks": 0,
        "orphaned_tool_results": 0,
        "omitted_tool_result_timestamps": 0,
        "invalid_source_timestamps": 0,
        "transformations": [
          "Moved Claude Code tool_result blocks to call-correlated ATIF observations."
        ]
      }
    }
  }
}
```

This data explains a conversion; it is not part of the ATIF standard and consumers may ignore it while still accepting the ATIF trajectory.

## Timestamp semantics

The preservation rule is: preserve when representable, report when not, never fabricate.

| Source situation | ATIF v1.7 result | Reported in `fidelity` |
| --- | --- | --- |
| Supported record with a valid ISO 8601 `timestamp` | Copied verbatim to that step's `timestamp` | not applicable (preserved) |
| Supported record with no `timestamp` | `Step.timestamp` is `null`; no time is substituted | not a loss |
| `timestamp` present but not a string or not valid ISO 8601 | `Step.timestamp` is `null`; the record is otherwise converted | `invalid_source_timestamps` |
| Timestamp on a record carrying a `tool_result` attached to a call | Not represented: `ObservationResult` has no timestamp field, and the call step keeps its own timestamp | `omitted_tool_result_timestamps` (one per attached result) |
| Timestamp on an unsupported or malformed record | Not represented; the record is not converted | `unsupported_source_records` |

ASB never derives a duration, start/end pair, or completion time from these values. Step timestamps are observed points, so downstream projections (see [OBSERVABILITY.md](OBSERVABILITY.md)) treat tool execution as having unknown duration.

## What ATIF does not establish

ATIF standardizes trajectory interchange. It does not specify a target product's native database schema, workspace binding, authorization, tool re-execution policy, or API for creating resumable sessions. ASB therefore treats target-native resumption as an explicit target-owned ingestion boundary.

The current Antigravity reference mapper has no evidenced representation for ATIF system messages. It omits those messages and reports the count to CLI callers instead of fabricating a target record type.

## Compatibility policy

Version 0.2 breaks the v0.1 ASEF output schema intentionally. Do not rename an ASEF file to `.atif.json`. Regenerate an ATIF document from the source transcript and inspect its ASB fidelity report.
