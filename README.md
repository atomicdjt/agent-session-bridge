# Agent Session Bridge

**Move structured coding-agent history between tools without collapsing everything into a prose summary.**

Agent Session Bridge is an MIT-licensed reference implementation for normalizing coding-agent session history into the **Agent Session Exchange Format (ASEF)**, with explicit fidelity/loss accounting and provider adapters.

> **Current status:** Claude Code JSONL import, ASEF normalization, heuristic secret redaction, loss reporting, and Antigravity derived-log export work today. Native Antigravity session rehydration is **not** currently supported because Antigravity does not expose a safe external session-import boundary.

## Why this exists

Coding agents can accumulate hours of structured state: messages, tool calls, tool results, timestamps, and execution context. Switching tools usually reduces that history to a hand-written or model-generated summary.

Agent Session Bridge explores a stricter question:

> **What coding-agent state can be transferred faithfully, what must be normalized, and what is inevitably lost?**

The project records those boundaries instead of pretending every provider has the same session model.

## What works today

| Capability | Status | Notes |
| --- | --- | --- |
| Claude Code JSONL import | ✅ | Parses supported message/tool structures into ASEF |
| Provider-neutral ASEF model | ✅ | Pydantic-validated, chronologically normalized representation |
| Fidelity/loss reporting | ✅ | Records unsupported/degraded structures rather than silently dropping them |
| Heuristic secret redaction | ✅ | Best-effort credential filtering; output still requires human review |
| Antigravity derived-log mapping | ✅ | Produces the documented `transcript.jsonl`-style target payload |
| Native Antigravity session import | ❌ blocked upstream | No supported API exists to reconstruct/resume external historical state |

## Quick start

### Install from this repository

This project is **not currently published on PyPI**. The PyPI distribution name `agent-session-bridge` is already used by an unrelated project, so **do not run `pip install agent-session-bridge` expecting this repository**.

```bash
git clone https://github.com/atomicdjt/agent-session-bridge.git
cd agent-session-bridge
python -m venv .venv
```

Activate the environment:

```bash
# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

Install the project:

```bash
python -m pip install -e .
```

Then inspect or convert a Claude Code transcript:

```bash
agent-session import --from claude-code --source your_claude_log.jsonl --report
agent-session convert --from claude-code --to antigravity your_claude_log.jsonl
agent-session handoff --from claude-code --to antigravity your_claude_log.jsonl
```

`handoff` currently returns `UnsupportedNativeImport` after producing the payload because native Antigravity history injection is blocked by the missing upstream import API.

## Architecture

```text
provider transcript
       │
       ▼
 source adapter
       │
       ▼
      ASEF ─────► loss report
       │
       ├────────► redacted portable representation
       │
       ▼
 target adapter
       │
       ▼
 target payload / supported importer
```

The implementation follows an extract-transform-export adapter model:

1. **Parser** — extracts provider-specific transcript structures.
2. **Canonical model** — validates and normalizes them into ASEF.
3. **Loss accounting** — records unsupported or degraded source information.
4. **Redaction** — applies best-effort secret/PII heuristics.
5. **Exporter** — maps ASEF into the target provider's supported representation.

## Fidelity model

When translating Claude Code to ASEF:

- **Preserved:** roles, ISO-8601 timestamps, plain text, tool names, tool arguments, supported tool results.
- **Normalized:** `parentUuid` chains are flattened into chronological ordering; provider-specific tool-result placement is mapped into canonical tool-result records.
- **Degraded/omitted:** provider metadata that has no stable target-independent meaning, including undocumented UI state and token metadata.
- **Unsupported:** unknown provider-specific block types are counted in the loss report instead of being silently treated as preserved.

The design principle is simple: **portability claims must be inspectable.**

## Antigravity integration boundary

The project can map ASEF into the derived `transcript.jsonl` structure emitted by Antigravity, but native resumption remains blocked.

Current Antigravity behavior relies on an internal SQLite conversation store with undocumented/opaque fields, and there is no supported `agy import-session` equivalent. Dropping a derived transcript into Antigravity's logs directory does not reconstruct a resumable historical session.

The project therefore does **not** mutate Antigravity's internal database or claim a working native handoff where none exists. It provides the reference payload and an integration RFC for a safer upstream ingestion boundary.

## Security boundary

- Imported history is processed as **data**. Historical commands are not executed.
- Secret redaction is heuristic and must not be treated as a guarantee.
- Never publish a converted transcript without reviewing it for credentials, personal data, private source, or proprietary context.
- The implementation does not reverse-engineer or write to Antigravity's opaque internal session database.

## Contributing

Useful contributions include:

- additional provider transcript fixtures and adapters;
- fidelity/loss-report improvements;
- redaction edge-case tests;
- target exporters for providers with documented ingestion formats;
- schema/versioning feedback;
- CLI ergonomics and documentation;
- reproducible evidence about which fields survive real cross-provider conversions.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution contract.

## Feedback wanted

The most useful criticism is technical and falsifiable:

- Which session fields should ASEF treat as durable state rather than provider noise?
- Where does the current fidelity model overstate preservation?
- Which provider should be the next source or target adapter?
- What minimum import API would a coding-agent runtime need for safe historical rehydration?

If this interoperability problem is useful to you, starring the repository helps other developers discover the reference implementation.

## License

MIT License. See [LICENSE](LICENSE).
