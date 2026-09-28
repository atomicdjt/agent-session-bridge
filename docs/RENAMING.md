# Project rename: Trajectory Fidelity Bridge

On September 28, 2026, this project was renamed from **Agent Session Bridge** to **Trajectory Fidelity Bridge (TFB)**.

The reason is straightforward: an older, unrelated public project was discovered using the former name in the same broad coding-agent session/interoperability space. The projects are unaffiliated. Renaming this project removes avoidable ambiguity and makes its distinct technical focus clearer.

## What this project is

Trajectory Fidelity Bridge is an ATIF-based reference implementation for portable coding-agent trajectories with explicit fidelity, provenance, loss accounting, redaction, and historical observability projection.

Its design deliberately distinguishes portable trajectory evidence from native resumable session state.

## Compatibility identifiers

Some machine-facing identifiers may retain the former wording temporarily so existing artifacts do not break without a migration path:

- PyPI distribution: `atomicdjt-agent-session-bridge`
- CLI entry point: `agent-session`
- ATIF extension namespace: `extra.agent_session_bridge`

The legacy PyPI distribution remains published at version 0.4.0 while new releases use `atomicdjt-trajectory-fidelity-bridge`. These identifiers are compatibility surfaces, not a statement of affiliation with the unrelated project.

When a machine-facing identifier is migrated, the project will preserve compatibility where practical and document the transition in the changelog.
