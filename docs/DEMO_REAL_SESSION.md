# Demonstrating ASB on a real Claude Code session

This is a private, reproducible procedure for turning a real Claude Code session into three things: an ATIF trajectory, a human-readable report, and an accounting of what the conversion could not preserve. It is built so that the raw session log stays private, and so that nothing is added to a public repository without a manual privacy review.

Running the procedure does not publish anything by itself; it only writes to the private root you give it. [`fixtures/real-session/`](../fixtures/real-session/README.md) is the one candidate that has, after that review, been sanitized, scanned, and added to this repository.

## What this fixture is and is not

- It comes from one controlled, real Claude Code 2.1.266 session — not a hand-written or model-generated source document.
- Its prompt, file data, paths, and identifiers are synthetic or pseudonymized: a made-up sandbox, a made-up inventory file, and every path, session ID, message ID, and tool-call ID replaced by the sanitizer before anything left the machine.
- It demonstrates the Claude Code adapter and `agent-session explain` path, and the fidelity limits that path explicitly reports on this session (see [`fixtures/real-session/README.md`](../fixtures/real-session/README.md) for the exact counts).
- It does **not** establish general compatibility for all Claude Code session types or versions. It is one session, one version, one operating system, and a handful of tools (`Read`, `Bash`, `Edit`, `Write`).

## What the demonstration shows

- **Conversion.** `agent-session import` converts Claude Code JSONL to ATIF v1.7, including `model_name` and token metrics on agent steps.
- **A readable account.** `agent-session explain` renders a timeline of steps with each tool call, its arguments, and its correlated result, including an error result and a call with no result.
- **Provenance.** Only what the ATIF document records, plus anything you supply in a clearly labelled, unverified manifest.
- **Limits.** A section derived from the converter's own fidelity counters: which records were not converted, which of those carry text and might be content loss, which fields on converted records were not carried, and what ATIF v1.7 cannot represent.

## The controlled session

A scripted session runs in a sandbox directory with three made-up inventory rows and a two-line notes file. One prompt makes Claude Code read a file, run a `Bash` command to total a column, attempt to read a file that does not exist (an intentional error), fix a typo with `Edit`, and `Write` a summary. The exact prompt is `PROMPT` in [`tools/private_demo.py`](../tools/private_demo.py). A controlled session keeps the trace free of real personal or project data, so the review is about the tooling, not about hiding anything.

## Run it

Claude Code must be signed in on the command line, which is separate from any desktop app sign-in. Do that yourself, in your own terminal:

```bash
claude auth login
```

Then run the demonstration. It needs the package installed from source (`python -m pip install -e .`):

```bash
python tools/private_demo.py --run-claude --scan-term <your-username> --scan-term <your-email>
```

To reuse a session that already exists, pass it read-only instead:

```bash
python tools/private_demo.py --source <path-to-session>.jsonl --scan-term <your-username>
```

`--scan-term` adds strings that must not appear anywhere in the candidate. Your OS user name, home directory, host name, `git config user.name` and `user.email`, `.claude`, and the private root name are always checked. The default private root is `C:/asb-demo`; use `--root` to change it. It must be outside this repository, and the command refuses a root inside it.

## What the command does

Each step prints counts only, never trace content.

1. Optionally runs the scripted session and locates its JSONL under `~/.claude/projects`.
2. Hashes and profiles the raw log. The raw file is opened read-only, is never copied, and its hash is checked again at the end.
3. Sanitizes it with an allowlist (below), then scans the result. If the scan fails, every candidate file is deleted and only the scan results remain.
4. Runs the real `agent-session import` and `agent-session explain` commands on the sanitized log.
5. Converts the raw log in memory only, and checks that the sanitized log gives the same fidelity counters and the same step structure.
6. Writes the review bundle.

## Output

Everything is written under `<root>/private/runs/<timestamp>/`:

| File | Contents |
| --- | --- |
| `candidate/sanitized.source.jsonl` | The sanitized Claude Code log. Present only if the scan passed. |
| `candidate/sanitized.atif.json` | The ATIF trajectory converted from it. |
| `candidate/report.md` | The Markdown report. |
| `candidate/manifest.json` | The sidecar of source-level facts: hash of the sanitized file, Claude Code version, converter version and commit, capture time, and a note giving the raw log's hash. |
| `scan_results.json` | Automatic findings: `FAIL` withholds the candidate, `REVIEW` needs a human look. |
| `field_drop_list.json` | Every record type reduced to a skeleton, every field replaced, every removed block part, pseudonymized identifiers, path substitutions, and which categories of content were **kept verbatim**. |
| `equivalence.json` | Raw-versus-sanitized comparison of fidelity counters and step structure, plus the raw log's own fidelity counters. |
| `raw_profile.json` | Record and block type counts of the raw log. |
| `private_run_notes.json`, `SHA256SUMS.txt` | Local paths, commands, and hashes. Keep these private. |

## How the sanitizer works

The sanitizer is an allowlist. Anything not listed is dropped, but the structure survives so the converter's accounting is unchanged.

- **Records.** Only `user`, `assistant`, and `system` records with a message are kept. Every other record (`attachment`, `file-history-snapshot`, `last-prompt`, `queue-operation`, titles, latches, and so on) becomes a type-only skeleton such as `{"type": "attachment"}`, so it is still counted as unsupported.
- **Fields.** On kept records only `type`, `timestamp`, `sessionId`, `version`, `gitBranch`, `cwd`, and `message` survive. Every other field, for example `uuid`, `parentUuid`, `requestId`, `toolUseResult`, keeps its name and its value becomes `[dropped]`. Inside `message` only `role`, `content`, `model`, `id`, and `usage` survive, and `usage` keeps only its four token counts.
- **Blocks.** `text`, `tool_use`, `tool_result`, and `thinking` are kept in reduced form. A thinking block keeps only whether it held text, and its signature is removed. Unknown block types become type-only skeletons.
- **Identifiers.** Message IDs, tool call IDs, and the session ID are replaced consistently, so correlation and the "same API response" relationship survive.
- **Paths.** Every spelling of the sandbox path becomes `/workspace`.
- **Kept verbatim.** User prompt text, assistant text, tool names and inputs, and tool results are kept as they are, because they are the substance of the demonstration. That content is what you review.

## Privacy review

The scan can only fail a candidate. A `PASS` means the automatic checks found nothing; it is not a clearance. Before any of this reaches a public repository, a person must:

1. Read every line of `sanitized.source.jsonl`. `field_drop_list.json` lists which categories of content were kept verbatim.
2. Read `scan_results.json`, including every `REVIEW` finding, and confirm each is intended.
3. Read `report.md` and `manifest.json`. The manifest note contains the raw log's hash, which identifies your private file to anyone who has it; decide whether that is acceptable.
4. Confirm the raw log is unchanged (`raw_unchanged_during_run` in `private_run_notes.json`).

Only after that review should a candidate be copied into a fixtures directory by hand. The tools never stage, commit, or push anything.

## Reading the report

- **Summary and Timeline.** One heading per ATIF step. A step that holds only a thinking block appears as empty, and says which API response it shares with other steps: Claude Code writes one record per content block, and ASB converts each to its own step. Merging them is not implemented.
- **Provenance.** "Recorded in the ATIF document" is what the document itself carries. "Supplied by the manifest" is shown only when you pass `--manifest` and is labelled unverified. "Not available" lists what nobody supplied. Nothing is inferred.
- **What this conversion could not preserve.** Derived only from the fidelity counters. Records are grouped as session metadata (no text-bearing field observed), records that may hold content (for example `attachment`), and unrecognized. A consistency check compares the counters with what the document actually contains.

## Known limits

- The report describes the conversion of the **sanitized** file. The equivalence check compares its fidelity counters and step structure with the raw log's, but text differs by pseudonyms, path substitution, and dropped thinking text.
- The record categories come from field names seen in Claude Code 2.1.x logs on one machine. They are an observation, not a specification, and a new Claude Code version may write record types that show up as `unrecognized`.
- Token metrics follow ATIF v1.7: `prompt_tokens` includes cached tokens. Claude Code's `input_tokens` excludes cache reads and cache creation (in the logs inspected it was 2 while cache reads were in the tens of thousands), so ASB adds them back. Cost is never computed.
- One API response spans several records, and ASB gives each its own step, so step counts are higher than the number of model responses. Usage is attached once per response.
- The sandbox path replacement handles the spellings a Windows session leaves (`C:\...`, `C:/...`, `/c/...`). Other environments may need `path_variants_for` extended.
- ASB's redaction is a heuristic and does not remove home-directory paths from tool text. The sanitizer does not rely on it.
- A demonstration on one controlled session is an example, not evidence of general compatibility.
