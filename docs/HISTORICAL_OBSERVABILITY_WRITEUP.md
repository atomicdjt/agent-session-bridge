# Reconstructing Agent Traces After the Fact Without Inventing Runtime Truth

## Executive summary

Agent Session Bridge (ASB) converts supported coding-agent transcripts into ATIF and can optionally project those ATIF trajectories into OpenTelemetry spans using OpenInference attributes. The important boundary is that this is **historical observability**, not original runtime instrumentation.

That distinction affects nearly every modeling decision:

- ATIF remains the portable source of truth.
- The OpenTelemetry trace is a downstream structural projection.
- Source-observed timestamps are preserved when present.
- Missing timing is not fabricated.
- Tool spans can therefore have zero duration when the transcript provides no independent tool-completion timestamp.
- Session identifiers are emitted only when the source actually provides one.
- Transcript content is excluded by default and requires an explicit privacy mode to export.

The objective is not to make a post-hoc trace look indistinguishable from a live trace. The objective is to make the distinction machine-readable and difficult to misinterpret.

## Why this problem exists

Coding agents increasingly leave useful structured history behind: messages, tool calls, tool results, timestamps, model metadata, and execution context. That history is valuable after the run for debugging, evaluation, interoperability, and incident review.

OpenTelemetry and OpenInference are natural destinations for that information because observability backends already understand traces and agent-oriented span attributes. But a transcript is not automatically a trace.

A live instrumentor observes execution boundaries while they happen. A post-hoc converter sees only what the historical artifact retained. Those are different evidence classes.

If a converter silently fills in missing duration, hierarchy, session identity, or content, it can create a trace that is visually persuasive but semantically stronger than the source evidence allows.

ASB therefore treats reconstruction as an evidence-preservation problem rather than a visualization problem.

## Architecture

```text
provider transcript
        |
        v
Agent Session Bridge parser / normalizer
        |
        v
ATIF v1.7 trajectory
        |
        +--> ASB fidelity + provenance metadata
        |
        v
historical observability projection
        |
        v
OpenTelemetry spans + OpenInference attributes
        |
        v
OTLP
        |
        v
Phoenix or another compatible backend
```

The projection is one-way. Observability does not replace the ATIF document and is not used as the canonical interchange record.

## What is preserved, transformed, and refused

### Preserved when available

- source `session_id` as `session.id`;
- step ordering;
- step source/role;
- source-observed ISO-8601 timestamps;
- tool names and tool-call identifiers;
- tool-call / observation correlation;
- provider and agent metadata available in the ATIF document.

### Transformed

- the trajectory becomes a root `CHAIN` span;
- each ATIF step becomes an `AGENT` span;
- each structured tool call becomes a `TOOL` span;
- transcript timestamps become OpenTelemetry span timestamps;
- optional text and tool payloads become OpenInference `input.value` / `output.value` attributes.

### Refused rather than fabricated

- a synthetic `session.id` when no real session identifier exists;
- a tool execution duration when the historical source does not contain an independent completion timestamp;
- timestamps for steps with no valid source-observed timezone-aware time;
- the claim that the reconstructed trace is equivalent to original in-process runtime instrumentation.

## Timing is the hardest semantic boundary

ATIF step timestamps are observed points. They are not necessarily execution intervals.

ASB currently requires every projected step to contain a timezone-aware source timestamp. The root trace boundaries are derived from the earliest and latest observed step timestamps. Each step is represented as a zero-duration point unless the source model can justify something stronger.

Tool calls are stricter still. If the ATIF observation result does not have its own independent timestamp, ASB cannot infer how long the tool ran. The corresponding `TOOL` span therefore uses the same start and end timestamp.

That is intentionally conservative.

A zero-duration historical tool span should be read as:

> "The historical record establishes that this tool call occurred at this observed point, but it does not establish an execution interval."

It should **not** be read as:

> "The tool executed instantaneously."

ASB makes the distinction explicit with:

- `agent_session_bridge.projection = historical` on the root span;
- `agent_session_bridge.timestamp.provenance = SOURCE_DERIVED` on the root boundary;
- `agent_session_bridge.timestamp.provenance = SOURCE_OBSERVED` on step and tool spans.

This is also why ASB rejects a missing or timezone-naive timestamp before exporting spans instead of silently substituting the current time.

The broader ecosystem is actively encountering the same ambiguity. OpenInference has an open issue, [Tool spans can report zero duration](https://github.com/Arize-ai/openinference/issues/3343), focused on live instrumentations where zero-duration spans can make latency unobservable. ASB's case is different: the duration is not observed in the historical evidence. The shared lesson is that consumers need to distinguish **measured zero** from **unknown interval represented as a point**.

## Privacy is part of the data model

Coding-agent transcripts routinely contain source code, credentials, commands, paths, proprietary material, and personal information. A historical observability converter should not treat content capture as an incidental exporter setting.

ASB exposes three explicit privacy modes:

### `metadata-only` (default)

Exports structure, roles, tool names, IDs, and other non-content metadata. Message text, tool arguments, and tool results are omitted.

### `redacted-content`

Exports textual content after ASB's heuristic redaction pass. This is useful for controlled debugging but is **not** a guarantee that every sensitive value has been removed.

### `full-content`

Exports the original supported content. This mode is deliberately opt-in because it may expose secrets, source code, proprietary context, filesystem paths, and personal information.

The test suite asserts that metadata-only mode does not emit planted sensitive strings and that redacted-content removes planted secret values while full-content preserves them.

## Relationship to Phoenix

Phoenix is especially relevant because it already supports several adjacent paths:

1. Phoenix has a public ATIF uploader that converts ATIF trajectories into OpenTelemetry-compatible spans and uploads them for visualization.
2. Phoenix maps ATIF `session_id` to OpenInference `session.id`.
3. Phoenix's own documentation describes ATIF as a proxy trajectory format for agent runs and supports subagents, continuation merging, deterministic IDs, and rich OpenInference mappings.
4. Phoenix has also documented server-side conversion of native OpenTelemetry GenAI semantic-convention attributes into OpenInference on ingest.

ASB and Phoenix therefore overlap at the **ATIF -> observability** boundary, but they have different responsibilities.

### Phoenix's center of gravity

Phoenix is an observability and evaluation backend. Its ATIF support is designed to ingest trajectories into Phoenix-native trace and experiment workflows.

### ASB's center of gravity

ASB is an interchange bridge. Its primary job is to normalize provider-specific coding-agent history into ATIF with explicit fidelity reporting. The observability layer is optional and deliberately generic: it projects the portable trajectory downstream rather than making Phoenix the canonical representation.

This separation matters because the same ATIF document should remain useful even if the destination is not Phoenix.

A particularly relevant current Phoenix roadmap issue is [capture ATIF as traces on the experiment](https://github.com/Arize-ai/phoenix/issues/15571), which states that when no live traces are emitted, ATIF should be used as a proxy for the agent trajectory. That is very close to the use case ASB implements from the interchange side.

Phoenix also has an active Harbor design that treats ATIF as the default trace mode when live OTLP instrumentation is unavailable. That design reinforces the same architectural pattern: historical trajectory data can be valuable observability evidence, but it is a different path from live instrumentation.

## Relationship to OpenInference

ASB uses stable OpenInference concepts where they fit:

| ASB / ATIF concept | Projection |
| --- | --- |
| source session identifier | `session.id` |
| trajectory root | `openinference.span.kind = CHAIN` |
| ATIF step | `openinference.span.kind = AGENT` |
| tool call | `openinference.span.kind = TOOL` |
| tool name | `tool.name` |
| tool-call identifier | `tool.id` |
| optional text content | `input.value` / `output.value` |

ASB keeps non-standard facts under its own namespace, for example:

- `agent_session_bridge.step_id`;
- `agent_session_bridge.step_source`;
- `agent_session_bridge.provider`;
- `agent_session_bridge.projection`;
- `agent_session_bridge.timestamp.provenance`.

That separation is intentional. ASB does not place provisional project-specific meanings into the `gen_ai.*` or OpenInference namespaces simply because a similar concept is under discussion elsewhere.

OpenInference's contribution guidance currently asks contributors to keep changes small and to open an issue before non-trivial feature work. It also states that the project is not actively accepting broad feature contributions. That makes an evidence-first integration note more appropriate than an unsolicited feature PR.

## Relationship to OpenTelemetry GenAI semantic conventions

The OpenTelemetry GenAI semantic-conventions work is moving quickly, especially around agents, execution identity, evidence origin, governance, durable runtime behavior, tool safety, and provenance.

Two areas are directly relevant to ASB but should not be conflated with existing stable semantics.

### Observation origin

The OpenTelemetry GenAI discussion [Evidence origin for governance-consumed GenAI telemetry](https://github.com/open-telemetry/semantic-conventions-genai/issues/386) is explicitly separating where an observation came from from who signed or attested it.

That distinction maps naturally onto historical reconstruction:

- a transcript field is **source-reported historical evidence**;
- a live OpenTelemetry SDK measurement is **runtime-observed telemetry**;
- an external monitor may provide a third vantage.

ASB does not currently emit the proposed `gen_ai.evidence.origin` attribute because the convention is still under discussion. Instead it uses the ASB namespace to avoid claiming standardization that does not yet exist.

### Durable agent execution

The OpenTelemetry discussion [observability semantics for durable agentic runtime execution](https://github.com/open-telemetry/semantic-conventions-genai/issues/462) highlights execution identity, checkpoint/resume, state transitions, non-linear causality, and external effects.

Those are important for live durable runtimes. A post-hoc ATIF projection may preserve some of the evidence needed to reconstruct them, but it should not invent those semantics when the source transcript lacks them.

Again, the rule is simple: **portable evidence first; standardized runtime claims only when the evidence supports them.**

## Comparison: live instrumentation vs historical projection

| Property | Live instrumentation | Historical projection |
| --- | --- | --- |
| sees execution in process | yes | no |
| can measure actual span duration | usually | only if source retained both boundaries |
| can propagate active trace context | yes | no; topology is reconstructed |
| can observe retries not written to transcript | potentially | no |
| can capture tool latency directly | yes | only if source recorded it |
| can preserve old runs after instrumentation was absent | no | yes |
| can normalize multiple provider transcript formats | not inherently | yes |
| should be treated as original runtime telemetry | yes, when correctly instrumented | no |

The two approaches are complementary rather than competing.

## What would falsify the current design

An evidence-first design should state what would cause it to change.

ASB's current timing model should be revisited if ATIF or a supported source adapter begins carrying independent, trustworthy tool start and completion timestamps. In that case, the projection could emit measured tool intervals instead of point spans.

The current root / step hierarchy should be revisited if a stable cross-framework convention emerges that better represents historical trajectory structure without implying live parent-child execution context.

The ASB-specific provenance attributes should be replaced or mapped if OpenTelemetry or OpenInference standardizes equivalent semantics with sufficiently clear definitions.

The Phoenix-specific example should remain an example, not a dependency, unless the project intentionally changes its architecture away from a backend-neutral observability projection.

## Validation checklist

A historical observability projection should be considered credible only if all of the following hold:

- [x] The portable trajectory validates against the ATIF model.
- [x] The projection preserves real session identifiers and omits synthetic ones.
- [x] Missing timestamps fail closed instead of being fabricated.
- [x] Timezone-naive timestamps are rejected.
- [x] Timestamp conversion preserves microsecond precision at the OpenTelemetry nanosecond representation.
- [x] Tool spans do not invent completion timing.
- [x] Metadata-only mode excludes transcript content.
- [x] Redacted-content and full-content modes are behaviorally distinct and tested.
- [x] Export failure state is tracked so a failed OTLP export is not reported as successful.
- [x] The documentation labels the output as a historical projection rather than original runtime telemetry.

## Open questions for external review

The most useful external feedback is narrow and falsifiable:

1. **Unknown duration:** Is a zero-duration point span plus explicit provenance the least misleading representation when only one source timestamp exists, or would an event / alternate representation be preferable?
2. **Topology:** Is `CHAIN -> AGENT -> TOOL` a reasonable structural projection for historical ATIF data when the hierarchy is clearly labeled non-runtime?
3. **Provenance namespace:** Until a stable OTel/OpenInference convention exists, are the ASB-specific `projection` and `timestamp.provenance` attributes sufficiently explicit?
4. **Phoenix interoperability:** Are there Phoenix ingestion or UI behaviors that could still cause historical point spans to be read as measured runtime durations?
5. **Privacy defaults:** Is metadata-only the right default for coding-agent transcripts, with all content capture opt-in?

## Reproduction

Install ASB with its optional observability dependencies:

```bash
python -m pip install -e ".[observability]"
```

For a local Phoenix receiver:

```bash
python -m pip install arize-phoenix
```

Then project an ATIF trajectory:

```bash
agent-session observe trajectory.atif.json \
  --from atif \
  --backend phoenix \
  --endpoint http://127.0.0.1:6006/v1/traces
```

The default privacy mode is `metadata-only`.

## Conclusion

Historical agent traces are useful precisely when original runtime instrumentation did not exist. That makes them valuable, but it also makes them easy to overstate.

The safest model is to preserve what the source proves, transform only what is necessary for interoperability, and attach explicit provenance to every inference introduced by the projection.

ATIF supplies the portable historical record. OpenTelemetry supplies the observability transport. OpenInference supplies useful agent-oriented span vocabulary. Phoenix supplies a concrete backend where the projection can be inspected.

Agent Session Bridge's job is to connect those layers without pretending that a reconstructed trace observed more than the transcript actually recorded.
