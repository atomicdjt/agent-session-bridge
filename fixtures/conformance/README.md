# Agent Session Bridge conformance fixtures

This directory contains small, synthetic ATIF v1.7 documents and one source/expected pair for adapter authors. The fixtures are intentionally provider-neutral: they exercise the portable trajectory contract and the namespaced `extra.agent_session_bridge` fidelity contract without claiming that any target can resume a native session.

## Cases

| Fixture | Purpose | Expected state |
| --- | --- | --- |
| `ordinary-turns.atif.json` | User and agent text turns | preserved |
| `tool-correlated-observations.atif.json` | One tool call with its correlated observation | preserved |
| `multiple-tool-calls.atif.json` | Multiple calls and results in one agent step | preserved |
| `chronological-normalization.source.jsonl` / `chronological-normalization.expected.atif.json` | Source records arrive out of timestamp order | normalized |
| `degraded-fidelity.atif.json` | A source record and blocks cannot be represented | degraded / unsupported |
| `target-omitted.atif.json` | A target cannot represent an ATIF system message | target-omitted |

The `.atif.json` files are complete documents and must validate with the official `atif` model. The chronological pair is deliberately explicit: the source ordering is not chronological, while the expected portable representation is. An adapter should only claim the `normalized` state when it actually performs that transformation and records it in its own fidelity report.

The manifest in `manifest.json` is the machine-readable index used by the conformance tests. All values are fictional. Do not add real transcripts, credentials, private source, or personal data.

## What the fixtures do not prove

Passing these fixtures proves only that an adapter can produce and inspect the represented ATIF structures and fidelity states. It does not prove native target import, historical session resumption, encryption, synchronization, or runtime observability.

