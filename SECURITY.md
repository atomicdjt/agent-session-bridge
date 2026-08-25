# Security Policy

Agent Session Bridge processes coding-agent transcripts that may contain credentials, private source material, personal data, proprietary context, or other sensitive information. Its redaction layer is deliberately described as **best effort**, not as a security guarantee.

## Supported scope

Security reports should target the current `main` branch or the latest tagged release. Reports about unsupported historical versions are still useful when they identify a flaw that may remain present in current code.

## Report a vulnerability privately

**Do not open a public issue containing vulnerability details, credentials, private transcripts, proprietary source, or other sensitive data.**

Use GitHub's **Report a vulnerability** control for this repository if it is available. If that control is not available, contact the maintainer privately through the contact channel published on the [atomicdjt GitHub profile](https://github.com/atomicdjt).

A useful report includes:

- the affected version or commit;
- the smallest reproducible example you can provide;
- expected and observed behavior;
- the security impact you believe is possible; and
- any mitigation or fix you have already tested.

Prefer synthetic fixtures. Do not send a real API key, access token, customer transcript, private repository content, or other secret merely to demonstrate the issue. If a real credential may have been exposed, revoke or rotate it before continuing the report.

## Security boundaries

- Imported transcript history is treated as data; historical commands are not executed by Agent Session Bridge.
- Secret redaction is heuristic and can miss sensitive material or over-redact benign material.
- Converted transcripts must be reviewed before publication, sharing, or ingestion into another system.
- `metadata-only` is the default observability privacy mode.
- `redacted-content` still depends on best-effort redaction.
- `full-content` is explicitly opt-in and can expose sensitive transcript content to the configured observability backend.
- Agent Session Bridge does not claim to make untrusted transcripts safe merely by converting them to ATIF.

See the [README security boundaries](README.md#fidelity-and-security-boundaries) and [observability documentation](docs/OBSERVABILITY.md) for the product's documented data-handling model.

## Coordinated disclosure

Please avoid publishing exploit details before a reasonable fix or mitigation can be evaluated. Security reports are assessed according to reproducibility, affected surface, realistic impact, and whether the behavior crosses a documented trust boundary.
