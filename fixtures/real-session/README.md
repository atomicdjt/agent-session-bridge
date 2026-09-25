# Real Claude Code session fixture

This fixture comes from one controlled, real Claude Code 2.1.266 session, not a hand-written or model-generated source document. Its prompt, file data, paths, and identifiers are synthetic or pseudonymized: the session ran in an empty sandbox directory against a made-up inventory CSV and a two-line notes file, and every path, session ID, message ID, and tool-call ID in the sanitized output has been replaced.

## Files

| File | Contents |
| --- | --- |
| `claude-code-controlled-demo.source.jsonl` | The sanitized Claude Code JSONL, reduced to an allowlist of fields. Records outside `user`/`assistant`/`system` are type-only skeletons (for example `{"type": "attachment"}`). On the remaining records, a field not on the allowlist keeps its name but its value is replaced with `"[dropped]"`, so the converter still counts it. |
| `claude-code-controlled-demo.atif.json` | The ATIF v1.7 trajectory produced by `agent-session import --from claude-code` from that source. |
| `claude-code-controlled-demo.manifest.json` | Source-level facts ATIF itself does not carry, for use with `agent-session explain --manifest`: the sanitized file's SHA-256, the real Claude Code version, the converter version and commit that produced it, and a capture timestamp. It intentionally does not contain the raw (pre-sanitization) session's hash, path, or any account, organization, or personal identifier. |

## What it demonstrates

This fixture demonstrates the Claude Code adapter path and its explicitly reported fidelity limits on one real session: 6 tool calls (`Read` ×3, `Bash`, `Edit`, `Write`) correlated with 6 results, including one intentional error (a `Read` of a file that does not exist), plus the harness's bookkeeping and attachment records that the converter does not convert. Run `agent-session explain fixtures/real-session/claude-code-controlled-demo.atif.json --manifest fixtures/real-session/claude-code-controlled-demo.manifest.json` to see the full account, or read [docs/DEMO_REAL_SESSION.md](../../docs/DEMO_REAL_SESSION.md) for how it was produced.

**It does not establish general compatibility.** It is one session, one Claude Code version, one operating system, and one small set of tools. It does not show how the converter behaves on other Claude Code versions, other tool types, subagent (sidechain) sessions, or non-English content.

## Provenance and privacy

The source JSONL was produced by an allowlist sanitizer (`tools/private_demo.py`, `tools/trace_sanitizer.py` in this repository) from a private raw session log that is not published. The sanitizer keeps the document's structure — record types, field names, block types, and call/result correlation — so that converting the sanitized file yields the same ASB fidelity counters and step structure as converting the raw file, while dropping every field not needed to demonstrate the converter. Before this fixture was added, the sanitized candidate was scanned for known secret shapes, emails, UUIDs, URLs, and absolute paths, and was reviewed by hand.

Do not add real transcripts, credentials, private source, or personal data to this directory.
