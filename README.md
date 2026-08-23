# Agent Session Bridge

**Move structured coding-agent history between tools without collapsing it into a prose summary.**

Agent Session Bridge is an MIT-licensed reference implementation for converting supported coding-agent transcripts into the [Agent Trajectory Interchange Format (ATIF)](https://github.com/harbor-framework/harbor/blob/main/rfcs/0001-trajectory-format.md). It is not a competing interchange standard.

> **Current status:** Claude Code JSONL normalization to ATIF v1.7, heuristic secret redaction, ASB fidelity reporting, and an Antigravity derived-log mapping are implemented. Native Antigravity session rehydration is not supported because Antigravity has no supported historical-session import boundary.

![Agent Session Bridge quick tour](docs/images/agent-session-bridge-quick-tour.gif)

*Animated architecture tour based on documented behavior; it is not a fabricated live screen recording.*

## What ATIF provides and what ASB adds

ATIF is the portable trajectory layer: ordered system/user/agent steps, structured tool calls, call-correlated observations, agent metadata, metrics, and a namespaced `extra` extension mechanism. ASB converts provider-specific transcript shapes into that public format.

ASB's distinct responsibilities are deliberately narrower:

- provider-specific parsing and normalization;
- best-effort secret redaction before export;
- transformation/fidelity accounting in `extra.agent_session_bridge`;
- target-specific mappings, such as the observed Antigravity derived-log shape; and
- explicit refusal to fabricate native resumable session state.

The current Antigravity reference mapper reports any ATIF system messages it cannot map to the observed derived-log shape; it does not silently invent a target record type.

See [the ATIF mapping](docs/FORMAT.md) and [layered architecture](docs/ARCHITECTURE.md) for exact preserved, transformed, and unsupported semantics.

## What works today

| Capability | Status | Notes |
| --- | --- | --- |
| Claude Code JSONL import | ✅ | Parses supported message and tool structures into ATIF v1.7 |
| Portable interchange document | ✅ | Validated by the official `atif` Python models |
| ASB fidelity reporting | ✅ | Namespaced provenance and unsupported/degraded source counts in ATIF `extra` |
| Heuristic secret redaction | ✅ | Best effort only; output still requires human review |
| Antigravity derived-log mapping | ✅ | Reference payload based on observed `transcript.jsonl` structures |
| Native Antigravity session import | ❌ blocked upstream | No supported API creates or resumes external historical state |

## Quick start

This project is not published as `agent-session-bridge` on PyPI; that name belongs to an unrelated project. Install from this repository with Python 3.11 or newer:

```bash
git clone https://github.com/atomicdjt/agent-session-bridge.git
cd agent-session-bridge
python -m venv .venv
```

Activate the environment, then install the package:

```bash
# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

python -m pip install -e .
```

Normalize a Claude Code transcript to an ATIF document, inspect ASB's source-fidelity report, or generate the Antigravity reference mapping:

```bash
agent-session import --from claude-code --source your_claude_log.jsonl --output trajectory.atif.json --report
agent-session convert --from claude-code --to antigravity your_claude_log.jsonl
agent-session handoff --from claude-code --to antigravity your_claude_log.jsonl
```

`handoff` returns `UnsupportedNativeImport` after producing the reference payload. It does not imply that Antigravity can resume the converted history.

## Architecture

```text
provider transcript
       │
       ▼
source parser and normalizer
       │
       ▼
ATIF trajectory ─────► ASB provenance/fidelity extension
       │
       ├──────────────► redacted portable trajectory
       │
       ▼
target-specific mapper
       │
       ▼
target payload / supported importer, if one exists
```

ATIF makes a trajectory portable; it does not require target runtimes to ingest it as native state. Native resumption remains a target-owned capability, with target-owned validation, persistence, and security constraints.

## Fidelity and security boundaries

For the current Claude Code adapter, ASB preserves supported roles, ISO-8601 timestamps, text, tool names, tool arguments, and tool results. It normalizes later Claude `tool_result` blocks into ATIF observations attached to their originating calls. Unsupported source records or blocks are counted in `extra.agent_session_bridge.fidelity`; they are never represented as successfully preserved.

- Imported history is processed as data. Historical commands are never executed.
- Redaction is heuristic and is not a guarantee.
- Do not publish a converted transcript without reviewing it for credentials, personal data, private source, or proprietary context.
- ASB does not reverse-engineer or write Antigravity's opaque internal session database.

## Optional observability projection

The observability implementation is an optional downstream projection of ATIF, not a replacement for ATIF, and not original runtime instrumentation. It is a historical structural projection.

```text
provider transcript
        ↓
Agent Session Bridge
        ↓
ATIF v1.7
        ↓
historical observability projection
        ↓
OpenTelemetry / OpenInference
        ↓
OTLP
        ↓
Phoenix or another compatible backend
```

To install the optional observability dependencies:

```bash
python -m pip install -e ".[observability]"
```

For the local Phoenix example, Phoenix may be installed separately. It is not required for core Agent Session Bridge operation:

```bash
python -m pip install arize-phoenix
```

A Claude Code source may also be observed using the existing supported `--from claude-code` path where appropriate.

```bash
agent-session observe trajectory.atif.json \
  --from atif \
  --backend phoenix \
  --endpoint http://127.0.0.1:6006/v1/traces
```

### Privacy

- `metadata-only` is the default.
- `redacted-content` exports redacted textual content.
- `full-content` must be explicitly selected and may expose sensitive transcript data. Treat `full-content` carefully.

### Historical timing

As this is a historical structural projection:
- ATIF Step timestamps may be represented as observed timing.
- Root boundaries may be derived from observed Step timestamps.
- Where independent tool completion timing is unavailable from ATIF, the projection does not pretend to have measured runtime duration.

For implementation details, see [docs/OBSERVABILITY.md](docs/OBSERVABILITY.md). For the evidence model, ecosystem comparison, limitations, and external-review questions, see [Reconstructing Agent Traces After the Fact Without Inventing Runtime Truth](docs/HISTORICAL_OBSERVABILITY_WRITEUP.md).

## Migration from v0.1 ASEF output

v0.2 removes the proprietary ASEF schema. Existing `*.asef.json` files are not ATIF documents and must not be relabeled as such. Re-run the original source transcript through `agent-session import` to produce a validated `*.atif.json` file, then review the ASB fidelity report. Python 3.11 is now the minimum supported version because the official ATIF models require it.

## Contributing

Useful contributions include provider transcript fixtures, source adapters, target mappings for documented ingestion boundaries, fidelity-report improvements, and reproducible evidence about real cross-provider transformations. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT License. See [LICENSE](LICENSE).
