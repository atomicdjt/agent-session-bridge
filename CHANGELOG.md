# Changelog

This file records user-visible changes in Agent Session Bridge releases.

## [0.4.0] - 2026-09-24

### Added

- `agent-session explain`, which renders an ATIF trajectory as a deterministic Markdown account of steps, tool calls, results, provenance, and conversion limits.
- Finer Claude Code fidelity evidence that distinguishes unsupported bookkeeping, potentially content-bearing records, unrecognized records, ignored fields, and duplicate usage records.
- A controlled real Claude Code fixture with synthetic data, pseudonymized identifiers, explicit provenance, and regression coverage.
- A private, local-only sanitizer and review procedure for preparing controlled real-session candidates without publishing raw logs.

### Changed

- Claude Code imports now carry observed model names and token usage into compatible ATIF step fields. Cost remains unavailable and is not inferred.

### Fixed

- The public real-session fixture preserves its source SHA-256 on Windows checkouts by pinning its JSONL line endings.
- Fixture regression tests now detect changed result content and tool-result correlation errors.

### Limitations

- The real-session fixture covers one controlled Windows session from Claude Code 2.1.266 using Read, Bash, Edit, and Write. It does not establish general compatibility across versions, operating systems, session shapes, or tools.
