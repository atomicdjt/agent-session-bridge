# Agent Session Bridge

Agent Session Bridge is a reference implementation for normalizing coding-agent session history into a versioned provider-neutral representation. It initially targets Claude Code JSONL import and explores the missing ingestion boundary required for resumable Antigravity session import.

## What works today
* **Canonical Interchange Format (ASEF):** Models provider-neutral conversation history, tracking user interactions, agent responses, and tool executions.
* **Claude Code Import:** Parses Claude Code JSONL into ASEF with high semantic fidelity, correctly flattening nested schemas and accurately modeling tool results.
* **Secret Redaction:** Provides a regex-based heuristic layer to redact credentials (e.g., API keys) from raw tool output.
* **Antigravity Derived-Log Mapping:** Translates ASEF into the `transcript.jsonl` log structure emitted by the Antigravity CLI.

## What does not work today
* **Native Antigravity Ingestion:** The Antigravity CLI relies on an undocumented internal SQLite conversation schema containing opaque/BLOB-encoded fields. There is no supported `agy import-session` command to securely reconstruct a session database from external logs. Dropping `transcript.jsonl` into the logs folder is ignored by the CLI on resumption. Thus, this project cannot natively inject a session; it serves as a reference implementation and payload generator proposing an upstream ingestion boundary.

## Motivation
A developer should be able to begin substantial work in one coding agent and transfer the structured state to another, avoiding the severe information loss of a summary-and-reprompt workflow. This project aims to demonstrate how this can be achieved safely across platforms.

## Architecture
The project follows a standard Extract-Transform-Load (ETL) adapter pattern:
1. **Parser:** Extracts provider-specific transcripts (e.g., Claude Code JSONL).
2. **Canonical Model:** Validates the data into the Agent Session Exchange Format (ASEF) using Pydantic, enforcing chronological normalization.
3. **Redaction:** Scrubs detected PII/secrets.
4. **Exporter:** Maps the ASEF schema to the target's derived-log structure (e.g., Antigravity `transcript.jsonl`).

## Quick Start
```bash
pip install agent-session-bridge
agent-session import --from claude-code --source your_claude_log.jsonl --report
agent-session convert --from claude-code --to antigravity your_claude_log.jsonl
agent-session handoff --from claude-code --to antigravity your_claude_log.jsonl
```
*(Note: `handoff` currently returns `UnsupportedNativeImport` and prints the payload, as native injection is blocked by upstream API limitations.)*

## Fidelity Model
When translating Claude Code to ASEF:
* **Preserved:** Roles, ISO-8601 timestamps, plain text content, tool names, tool arguments.
* **Normalized:** `parentUuid` chains flattened to chronological lists; Claude user-role tool results mapped to standalone system tool results.
* **Degraded/Omitted:** Token metadata, undocumented proprietary UI states.
* **Unsupported:** Any unknown provider-specific block types are tallied in the Loss Report.

## Antigravity Integration Status
Currently **RFC Ready**. The project successfully maps external history to the derived log schema used by Antigravity, but native insertion into the CLI's SQLite store requires a supported API. The use of `agy --input-format stream-json` does not solve this problem, as it is designed for forward-feeding live turns rather than reconstructing historical assistant state.

## Security
* This tool processes untrusted input as data. It does not execute imported historical commands.
* Redaction heuristically removes secrets, though it should not be relied upon exclusively. Always verify output before publishing.
* No internal Antigravity databases are dangerously mutated or reverse-engineered.

## Contributing
See `CONTRIBUTING.md`.

## License
MIT License.
