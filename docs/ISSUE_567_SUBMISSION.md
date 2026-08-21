# Reference Implementation & Ingestion RFC

Hi everyone — building on the provenance/fail-closed discussion above, I built and adversarially tested a reference implementation for the **external side** of this request: [Agent Session Bridge](https://github.com/atomicdjt/agent-session-bridge).

It currently provides:

- a versioned provider-neutral session model (ASEF);
- a Claude Code JSONL importer with explicit preservation/loss accounting;
- normalization of visible turns and tool/result records;
- heuristic credential redaction; and
- a reference mapping to Antigravity's observed derived `transcript.jsonl` structures.

The most useful result was actually a failed assumption. During ablation testing on `agy` **1.1.17 / Windows**, a synthesized `.system_generated/logs/transcript.jsonl` was **not** resumable with `agy --conversation`; the CLI returned `conversation not found`. Normal CLI-created conversations were observed to use Antigravity-managed SQLite persistence under `~/.gemini/antigravity/conversations/`, with opaque/BLOB-encoded fields and undocumented creation invariants. I therefore stopped at that boundary rather than mutating internal databases.

That seems to leave the same narrow missing primitive identified in this issue: a supported Antigravity-side import boundary that accepts validated historical state, reports unsupported/degraded records explicitly, preserves provenance/workspace association where possible, and returns a normal resumable conversation ID. Historical tool calls should be display/state records, not replayed actions.

I also tested `--input-format stream-json`; on 1.1.17 it supports driving new/live turns, but did not provide a way to reconstruct externally generated prior assistant/tool history as imported native history.

Artifacts:
- **Repository:** https://github.com/atomicdjt/agent-session-bridge
- **Integration RFC:** https://github.com/atomicdjt/agent-session-bridge/blob/main/docs/ANTIGRAVITY_INTEGRATION.md
- **Verification / ablation report:** https://github.com/atomicdjt/agent-session-bridge/blob/main/docs/VERIFICATION_REPORT.md
- **Reproduction guide:** https://github.com/atomicdjt/agent-session-bridge/blob/main/docs/EXPERIMENT_REPRO.md

Feedback or corrections on the proposed boundary are very welcome.
