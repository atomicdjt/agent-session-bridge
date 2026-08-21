# Antigravity Integration RFC

## Motivation
Developers frequently switch between agentic environments (e.g., Claude Code to Antigravity) during complex tasks. While agent-session-bridge demonstrates high-fidelity extraction of session history into a canonical format (ASEF) and maps it to Antigravity's `transcript.jsonl` structure, native resumption is currently blocked. Antigravity's `--conversation` flag relies on an undocumented internal SQLite schema containing opaque/BLOB-encoded fields, and dropping a derived log file into `.system_generated` is ignored.

## Proposed Upstream Capability
We propose adding an explicit `import-session` boundary to the `agy` CLI to deserialize structured JSONL histories securely into the SQLite representation.

### Proposed Interface
```bash
agy import-session \
  --source <file.jsonl> \
  --format <format> \
  [--dry-run]
```

### Output Behavior
```json
{
  "conversation_id": "new-uuid-1234",
  "status": "imported",
  "warnings": [
    "Unrecognized tool execution dropped"
  ]
}
```

### Security Boundaries
* The CLI must validate all inbound historical structures.
* Historical tool outputs must never be re-executed during ingestion.
* The ingestion must occur within the boundary of the `agy` runtime, ensuring internal DB migrations and binary blob creation are managed by the official system, rather than via external mutations.

## Why `--input-format stream-json` is Insufficient
Testing confirms that `--input-format stream-json` is designed to drive the live loop (taking stdin inputs and processing them as new future turns). It does not allow for reconstructing arbitrary historical state (such as past assistant text and matched tool responses) as an authoritative native history. Session migration remains a distinct capability requiring a dedicated ingestion path.
