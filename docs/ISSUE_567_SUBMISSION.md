# Reference Implementation & Ingestion RFC

Hi everyone,

I built and adversarially tested a reference implementation for the external side of this feature request (`agent-session-bridge`), focusing on normalizing Claude Code JSONL history and mapping it to Antigravity's `.system_generated/logs/transcript.jsonl` structure.

**What was implemented:**
* A canonical, versioned Agent Session Exchange Format (ASEF) using strict Pydantic schemas.
* A Claude Code importer with explicit preservation/loss accounting (flattening nested tool schemas, extracting user-role tool results safely).
* Security redaction (regex heuristics for credentials).
* An exporter that maps canonical turns to Antigravity's observed derived-log format (`USER_EXPLICIT`, `PLANNER_RESPONSE`, `TOOL_RESPONSE`).

**Important verification result:**
During adversarial validation, I discovered through ablation testing that placing a `transcript.jsonl` into the `.system_generated/logs` directory is ignored by `agy --conversation` on resumption. The authoritative native CLI state resides entirely within Antigravity's internal SQLite persistence mechanism (`~/.gemini/antigravity/conversations/`), which uses an undocumented schema containing opaque/BLOB-encoded fields. To respect the tool's engineering boundaries, this reference implementation intentionally does not attempt to mutate or reverse-engineer these databases.

**Missing primitive:**
The remaining requirement appears to be a supported Antigravity-side ingestion boundary capable of accepting validated external historical logs and safely constructing the internal representation, returning a resumable conversation ID.

*(Note: Testing on `agy` v1.1.17 confirms that `--input-format stream-json` drives programmatic injection of live/future turns, but does not reconstruct pre-existing historical assistant/tool state as authoritative native history. Session migration therefore remains a distinct capability.)*

I've written up the findings, reproduction steps, and a proposed `agy import-session` RFC:
* **Repository:** https://github.com/atomicdjt/agent-session-bridge
* **Integration RFC:** https://github.com/atomicdjt/agent-session-bridge/blob/main/docs/ANTIGRAVITY_INTEGRATION.md
* **Verification & Ablation Report:** https://github.com/atomicdjt/agent-session-bridge/blob/main/docs/VERIFICATION_REPORT.md
* **Independent Reproduction Guide:** https://github.com/atomicdjt/agent-session-bridge/blob/main/docs/EXPERIMENT_REPRO.md

Feedback or technical corrections on the integration boundary proposal are welcome.
