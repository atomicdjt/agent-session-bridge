# Reference Implementation & Ingestion RFC

Hi everyone,

I built and adversarially tested a reference implementation for the external side of this feature request (`agent-session-bridge`), focusing on normalizing Claude Code JSONL history and mapping it to Antigravity's `.system_generated/logs/transcript.jsonl` structure.

**What was implemented:**
* A canonical, versioned Agent Session Exchange Format (ASEF) using strict Pydantic schemas.
* A Claude Code importer with explicit preservation/loss accounting (flattening nested tool schemas, extracting user-role tool results safely).
* Security redaction (regex heuristics for credentials).
* An exporter that maps canonical turns to Antigravity's derived log format (`USER_EXPLICIT`, `PLANNER_RESPONSE`, `TOOL_RESPONSE`).

**Important verification result:**
During validation, I discovered through ablation testing that placing a `transcript.jsonl` into the `.system_generated/logs` directory is ignored by the CLI on resumption (`agy --conversation`). The true native CLI state currently resides entirely within the internal SQLite persistence mechanism (`~/.gemini/antigravity/conversations/`), which utilizes undocumented binary schemas. To respect the tool's engineering boundaries, this reference implementation intentionally does not attempt to mutate or reverse-engineer these SQLite databases.

**Missing primitive:**
The remaining requirement appears to be a supported Antigravity-side ingestion boundary capable of accepting validated external historical logs (e.g., JSONL) and safely reconstructing them into the SQLite backend, returning a resumable conversation ID. 

*(Note: My testing confirms that the current `--input-format stream-json` solves programmatic injection of live/future turns, but does not reconstruct pre-existing historical assistant/tool state as authoritative native history.)*

I've written up the findings, reproduction steps, and a proposed `agy import-session` RFC here:
* **Repository & RFC:** [Link to Repository]
* **Verification & Ablation Report:** [Link to VERIFICATION_REPORT.md]

Feedback or technical corrections on the integration boundary proposal are welcome.
