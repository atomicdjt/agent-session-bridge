# Security Considerations

## Protections Implemented
* **Passive Processing:** Imported transcript text and tool results are strictly treated as data. Historical commands are never executed during the ingestion or conversion process.
* **Redaction Heuristics:** The `security.redact` module employs regex-based scanning to replace credential-like values with `[REDACTED]`. It traverses ATIF strings, multimodal `ContentPart` values, tool arguments, and ASB extension values; `workspace.cwd` is omitted from redacted output. See [What redaction covers](#what-redaction-covers).
* **Safe Deserialization:** Parsing relies exclusively on standard JSON and Pydantic validation. No untrusted pickle-like formats, `eval`, or `exec` are utilized.

## What redaction covers

Redaction is pattern matching, not secret detection. It is tested only against synthetic values.

**Matched by name.** A `KEY=value`, `KEY: value`, `--flag value`, or JSON/dict key is treated as sensitive when the name *ends with* `api key`, `access key`, `secret key`, `private key`, `secret`, `token`, `password`, `passwd`, or `credential(s)`, including prefixed names such as `OPENAI_API_KEY`, `GITHUB_TOKEN`, or `client_secret`. Quoted and unquoted values are handled; values shorter than 10 characters after `=`/`:` are intentionally left alone to avoid destroying prose (`token=short`). Structured `authorization`, `bearer`, and `cookie` keys are also matched by name.

**Matched by form.** `Authorization:` headers with any scheme, `Cookie:`/`Set-Cookie:` headers, `Bearer` tokens, `--token VALUE`-style CLI flags, URL user-info (`scheme://user:secret@host`), `curl -u user:secret`, one level of JSON-escaped `\"key\": \"value\"` pairs, PEM private-key blocks (an unterminated block is redacted to the end of the text), and a few well-known token shapes (GitHub, `sk-`, Slack, AWS access-key IDs, JWTs).

**Not claimed.** Short secrets, secrets under names outside the list above, values that begin with `$` (treated as a variable reference) or a quote/delimiter character, attached short flags such as `mysql -pSECRET`, npm/PyPI/cloud tokens without a listed shape, multiply-escaped or encoded values, and secrets embedded in prose, source code, or binary data are not reliably detected. Names ending in a matched term can also over-redact (`csrf_token`, `next_page_token`). Review converted transcripts before sharing them.

## Risks Mitigated
* **Malformed Input:** Truncated or invalid JSON lines, valid non-object JSON values, and unsupported source records are counted in `extra.agent_session_bridge.fidelity` rather than reaching field access.
* **Internal State Corruption:** The project explicitly declines to modify Antigravity's internal SQLite database, mitigating the risk of corrupting developer workspaces.

## Risks Not Solved
* **Targeted Prompt Injection:** If a historical tool output contained a prompt injection attack, the converted log will still carry that text. If later loaded by an agent, it could theoretically trigger agentic action.
* **Incomplete Redaction:** The redaction layer is heuristic and may miss novel or highly specific secret formats. Users must manually review payloads before publication.

## Responsible Reporting
If you discover a vulnerability, do not open a public issue. Please refer to standard open-source responsible disclosure practices.
