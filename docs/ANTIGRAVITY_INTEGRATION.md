# Antigravity Integration RFC

## Motivation
Developers frequently switch between agentic coding environments during complex tasks. Agent Session Bridge normalizes supported Claude Code history into the Agent Trajectory Interchange Format (ATIF) and maps that portable trajectory to Antigravity's observed derived `transcript.jsonl` log structure.

Testing with Antigravity CLI 1.1.17 on Windows found that a synthesized derived log alone is not accepted by `agy --conversation` as resumable history. Normal CLI-created conversations were observed to use Antigravity-managed SQLite persistence under `~/.gemini/antigravity/conversations/`, including opaque/BLOB-encoded fields and invariants that are not documented as a supported external creation contract. This RFC therefore proposes a supported ingestion boundary rather than attempting to reproduce internal persistence externally.

## Proposed Upstream Capability
Add an explicit historical-session import boundary to `agy` that accepts validated external session data and returns a normal resumable conversation ID. The implementation of Antigravity's internal persistence remains entirely behind the CLI/runtime boundary.

### Proposed Interface
```bash
agy import-session \
  --source <file.jsonl> \
  --format <format> \
  [--dry-run]
```

### Example Output
```json
{
  "conversation_id": "new-uuid-1234",
  "status": "imported",
  "warnings": []
}
```

For incomplete or unsupported input, the command should report preservation/loss explicitly. For handoff use cases, fail-closed behavior is preferable when required history cannot be represented faithfully.

### Suggested Contract
* Validate all inbound historical structures before creating a conversation.
* Preserve visible user/assistant history and supported tool/result records where possible.
* Preserve or explicitly report workspace/project association.
* Mark imported provenance so hosts can distinguish imported from native-origin history.
* Treat historical tool calls as records; never re-execute them during ingestion.
* Return a stable conversation ID usable by the normal `agy --conversation <id>` path.
* Report skipped, unsupported, redacted, or degraded records explicitly.
* Keep all internal persistence creation/migration inside the supported Antigravity runtime boundary.

## Why `--input-format stream-json` Does Not Replace Historical Import
Testing on `agy` 1.1.17 found that `--input-format stream-json` can drive new/live turns programmatically. It did not provide a mechanism for reconstructing externally generated prior assistant responses and tool/result history as imported native history. Historical session migration therefore remains a distinct capability in the tested version.

## Reference Implementation
Agent Session Bridge provides the external-side reference pipeline for this proposal:

`Claude Code JSONL -> ATIF -> ASB validation/fidelity accounting -> Antigravity derived-log mapping`

The project intentionally stops at the unsupported native-ingestion boundary. The derived-log mapping is evidence and interoperability tooling, not a claim that `transcript.jsonl` is an official import format.
