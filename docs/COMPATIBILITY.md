# Compatibility Matrix

| Source      | Import           | Export           | Native resume        |
| ----------- | ---------------- | ---------------- | -------------------- |
| Claude Code | **VERIFIED**     | TBD              | N/A                  |
| Antigravity | TBD              | **VERIFIED**     | BLOCKED BY CLI API   |
| Codex       | Experimental/TBD | Experimental/TBD | capability-dependent |

*Note: Antigravity export generates derived-log JSONL payloads mapped to observed transcript structures. Native ingestion is blocked by the absence of a supported `agy import-session` CLI boundary. The derived log format is not known to constitute the authoritative native conversation-ingestion schema.*
