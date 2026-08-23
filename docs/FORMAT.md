# ATIF Interchange and ASB Extension Profile

Agent Session Bridge emits a valid [ATIF v1.7](https://github.com/harbor-framework/harbor/blob/main/rfcs/0001-trajectory-format.md) `Trajectory` as its portable output. This document records the exact mapping and labels the parts that remain ASB-specific.

## ASEF migration map

| Former ASEF concept | ATIF v1.7 representation | Transform or limitation |
| --- | --- | --- |
| `ASEFSession.schema_version` | `Trajectory.schema_version = "ATIF-v1.7"` | Replaced; ASEF version is not carried forward |
| `session_id` | `Trajectory.session_id` | Preserved when the source supplies it |
| `source.agent` / `source.version` | `Trajectory.agent.name` / `agent.version` | Preserved as `claude-code` and its source version |
| `source.provider` | `Trajectory.agent.extra.provider` | ATIF extension; no custom ASB schema |
| `Turn` role, time, text | `Step.source`, `timestamp`, `message` | Preserved for supported records |
| `ToolInvocation` | agent-step `tool_calls` | Preserved with ID, name, and JSON arguments |
| `ToolResult` | originating agent-step `observation.results` | Normalized from Claude's later user block; correlated by `source_call_id` |
| `Workspace` / repository metadata | `extra.agent_session_bridge.workspace` | ATIF has no portable workspace contract; source-derived metadata only |
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
        "transformations": [
          "Moved Claude Code tool_result blocks to call-correlated ATIF observations."
        ]
      }
    }
  }
}
```

This data explains a conversion; it is not part of the ATIF standard and consumers may ignore it while still accepting the ATIF trajectory.

## What ATIF does not establish

ATIF standardizes trajectory interchange. It does not specify a target product's native database schema, workspace binding, authorization, tool re-execution policy, or API for creating resumable sessions. ASB therefore treats target-native resumption as an explicit target-owned ingestion boundary.

The current Antigravity reference mapper has no evidenced representation for ATIF system messages. It omits those messages and reports the count to CLI callers instead of fabricating a target record type.

## Compatibility policy

Version 0.2 breaks the v0.1 ASEF output schema intentionally. Do not rename an ASEF file to `.atif.json`. Regenerate an ATIF document from the source transcript and inspect its ASB fidelity report.
