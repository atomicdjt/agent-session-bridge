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

## Fidelity breakdown

`unsupported_source_records` and `unsupported_source_blocks` remain the totals. The breakdown below says *what* those totals contain, so bookkeeping is not mistaken for content loss, and content loss is not hidden inside a bookkeeping count. All lists are sorted by name so the report is deterministic.

| Field | Meaning |
| --- | --- |
| `unsupported_record_types` | Records not converted, as `{type, category, records}`. `system` records are labelled `system/<subtype>`. |
| `unsupported_block_types` | Content blocks not converted, as `{type, blocks, with_content}`. |
| `ignored_fields` | Fields present on *converted* records that ATIF has no place for and ASB did not carry (for example `toolUseResult`, `parentUuid`, `message.stop_reason`), as `{field, records}`. Counted per record, not per value. |
| `synthetic_agent_records` | Agent records whose model is `<synthetic>`: messages the Claude Code client generated (for example an authentication failure), not model output. |
| `duplicate_usage_records`, `conflicting_usage_records` | See [Model and usage](#model-and-usage). |

**Record categories** come from the field names observed on real Claude Code 2.1.x logs. They are an observation about those logs, not a Claude Code specification:

| Category | Meaning | Types classified this way |
| --- | --- | --- |
| `bookkeeping` | No text-bearing field was observed; session metadata only. | `agent-name`, `ai-title`, `atis-latch`, `bridge-session`, `cost-state`, `custom-title`, `file-history-delta`, `file-history-snapshot`, `mode`, `permission-mode`, `pr-link`, `system/turn_duration` |
| `text_bearing` | Observed with text or content fields, such as context the harness supplied to the model, echoed prompts, or hook output. ASB cannot show that dropping these loses nothing. | `attachment`, `last-prompt`, `queue-operation`, `system/compact_boundary`, `system/local_command`, `system/stop_hook_summary` |
| `unrecognized` | Not in either list, or malformed. Treated as possible content loss. | everything else |

A `thinking` block counts as `with_content` only when its `thinking` text is non-empty; an empty one holds only an opaque signature. Every other unconverted block type is assumed to carry content, because ASB cannot show otherwise.

## Model and usage

For agent records, `message.model` becomes `Step.model_name`. The `usage` object becomes `Step.metrics` in **tokens** (ATIF v1.7 has no other unit here):

| ATIF v1.7 `Metrics` field | Claude Code `usage` source |
| --- | --- |
| `prompt_tokens` | `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` |
| `cached_tokens` | `cache_read_input_tokens` |
| `completion_tokens` | `output_tokens` |
| `extra.uncached_input_tokens`, `extra.cache_creation_input_tokens` | the two source counts that ATIF has no field for |
| `cost_usd` | never set; Claude Code records carry no per-step cost |

ATIF defines `prompt_tokens` as all input tokens including cached ones, while Anthropic's `input_tokens` excludes cache reads and cache creation, so both are added back. Claude Code writes one record per content block and repeats the response's `usage` on each of them. Metrics are attached only to the first record of each API response (`message.id`), so summing per-step metrics gives the response totals. A later record whose usage is identical counts as `duplicate_usage_records`; one whose usage differs keeps the first record's values and counts as `conflicting_usage_records`. A record with a missing or invalid usage value gets a model name and no metrics. No `final_metrics` are written.

Each step also carries `extra.agent_session_bridge.source_line` (1-based ordinal among the source's non-blank lines, the convention the interoperability oracle uses) and, for agent steps, `source_message_id`.

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
