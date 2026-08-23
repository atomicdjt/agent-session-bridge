# Verification Report

> The Antigravity experiments below are historical evidence about the native-import boundary. Current v0.2 portable output is ATIF v1.7; see `docs/FORMAT.md` for the current mapping and fidelity contract.

## 1. Environment Details
* **Antigravity Product:** Antigravity CLI (`agy`)
* **Version:** `1.1.17`
* **Operating System:** Windows
* **Python Version:** 3.14.7
* **Observed filesystem roots:**
  * App data: `~/.gemini/antigravity/`
  * Conversation databases: `~/.gemini/antigravity/conversations/`
  * Derived transcripts: `~/.gemini/antigravity/brain/<uuid>/.system_generated/logs/`

## 2. Methodology & Ablation Results
I performed controlled ablation experiments to characterize persistence behavior observed in Antigravity CLI 1.1.17 on Windows.

1. **Experiment A (transcript JSONL only):** Created `transcript.jsonl` in a fresh UUID directory.
   *Result:* `agy --conversation <uuid>` returned `warning: conversation not found`. **Failed.**
2. **Experiment B (SQLite DB inspection):** Used Python's `sqlite3` module to inspect the schema of a newly generated `conversations/<uuid>.db`.
   *Result:* Observed tables including `trajectory_meta`, `steps`, and `gen_metadata`, with opaque/BLOB-encoded fields whose external creation contract is undocumented.
3. **Experiment C (SQLite copied UUID):** Copied a valid SQLite DB to a new UUID filename and attempted resumption.
   *Result:* `agy` returned `Error: trajectory not found`. **Failed.**

**Finding:** In this environment, a derived `transcript.jsonl` file alone is not accepted as resumable conversation state. Resumable conversations were observed to depend on Antigravity-managed SQLite persistence under `conversations/`, with additional invariants not documented as a supported external creation interface. These experiments do not claim to exhaustively characterize Antigravity's internal architecture.

## 3. Field-Level Fidelity (Claude Code -> ATIF -> Antigravity derived-log JSONL)
* **Preserved in current fixtures:** Turn roles, ISO-8601 timestamps, plain text content, tool names, tool arguments, and call-correlated tool results.
* **Normalized:** Claude tool results attached to later `user` messages become ATIF observations on the originating agent call, then derived-log tool-response records.
* **Degraded / Omitted:** Raw token metrics are not populated by the current adapter. Unrecognized source records or blocks are counted in `extra.agent_session_bridge.fidelity`.
* **Synthesized:** `step_index` and generic statuses such as `DONE` are generated for the Antigravity derived-log representation.

This mapping is a reference transformation to observed derived-log structures; it is not a native Antigravity ingestion format.

## 4. Parser Resilience
* **Malformed JSON / truncated lines:** Caught via `JSONDecodeError` and reported through loss accounting.
* **Credential redaction:** The `redact_trajectory` heuristic is tested against an intentionally synthetic `api_key` value while preserving valid ATIF structure.
* **Huge records:** Each JSONL record is parsed as a complete line, so maximum record size remains bounded by available memory.

## 5. Corrected Conclusions
* **Disproved:** Generating `transcript.jsonl` is sufficient for native handoff. The tested CLI did not resume from the synthetic log-only state.
* **Not established:** Production-ready Claude Code -> Antigravity native handoff. No supported external historical-session ingestion boundary was identified.

## 6. Final Readiness Classification
**RFC READY**

The codebase provides a tested Claude Code -> ATIF normalization pipeline with explicit ASB fidelity accounting, redaction, and a reference mapping to observed Antigravity derived-log structures. Native Antigravity ingestion is intentionally not implemented because no supported external creation/import interface was identified in the tested CLI. The repository therefore serves as a reference implementation, verification artifact, and proposed upstream API contract rather than a completed native handoff system.
