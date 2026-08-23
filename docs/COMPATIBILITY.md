# Compatibility Matrix

| Source or target | Portable trajectory | Target mapping | Native resume |
| --- | --- | --- | --- |
| Claude Code | **Verified:** supported JSONL records normalize to ATIF v1.7 | N/A | N/A |
| Antigravity | N/A | **Verified:** reference derived-log payload | **Blocked:** no supported historical-session import API identified |
| Codex | Not implemented | Not implemented | Capability-dependent and unverified |

Antigravity export is a mapping to observed derived-log JSONL structures, not a claim that the log is an authoritative native ingestion schema. ATIF portability does not change that boundary.
