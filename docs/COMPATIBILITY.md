# Compatibility Matrix

| Source      | Import           | Export           | Native resume        |
| ----------- | ---------------- | ---------------- | -------------------- |
| Claude Code | **VERIFIED**     | TBD              | N/A                  |
| Antigravity | TBD              | **VERIFIED**     | BLOCKED BY CLI API   |
| Codex       | Experimental/TBD | Experimental/TBD | capability-dependent |

*Note: Antigravity export generates perfectly mapped JSONL payloads, but native ingestion is blocked by the lack of an `agy import-session` CLI interface.*
