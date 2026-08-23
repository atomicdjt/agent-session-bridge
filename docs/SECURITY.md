# Security Considerations

## Protections Implemented
* **Passive Processing:** Imported transcript text and tool results are strictly treated as data. Historical commands are never executed during the ingestion or conversion process.
* **Redaction Heuristics:** The `security.redact` module employs regex-based scanning to replace common credential patterns (e.g., standard API keys and bearer tokens) with `[REDACTED]`. It traverses ATIF strings, multimodal `ContentPart` values, tool arguments, and ASB extension values; `workspace.cwd` is omitted from redacted output.
* **Safe Deserialization:** Parsing relies exclusively on standard JSON and Pydantic validation. No untrusted pickle-like formats, `eval`, or `exec` are utilized.

## Risks Mitigated
* **Malformed Input:** Truncated or invalid JSON lines, valid non-object JSON values, and unsupported source records are counted in `extra.agent_session_bridge.fidelity` rather than reaching field access.
* **Internal State Corruption:** The project explicitly declines to modify Antigravity's internal SQLite database, mitigating the risk of corrupting developer workspaces.

## Risks Not Solved
* **Targeted Prompt Injection:** If a historical tool output contained a prompt injection attack, the converted log will still carry that text. If later loaded by an agent, it could theoretically trigger agentic action.
* **Incomplete Redaction:** The redaction layer is heuristic and may miss novel or highly specific secret formats. Users must manually review payloads before publication.

## Responsible Reporting
If you discover a vulnerability, do not open a public issue. Please refer to standard open-source responsible disclosure practices.
