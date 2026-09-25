"""One reproducible, private demonstration of Agent Session Bridge on a real session.

    python tools/private_demo.py --run-claude --scan-term <your-username> ...
    python tools/private_demo.py --source <session>.jsonl --scan-term <your-username> ...

Pipeline (every step prints counts only, never trace content):

1. optionally run a scripted, harmless Claude Code session in a sandbox directory;
2. hash and profile the raw JSONL, which is only ever opened read-only and is never copied;
3. sanitize it with an allowlist, scan the result, and withhold everything if the scan fails;
4. convert the sanitized log with the real ``agent-session import`` and ``explain`` commands;
5. check that the sanitized log yields the same fidelity accounting as the raw one;
6. write a candidate bundle, a field-drop list, and scan results under the private root.

The private root must be outside this repository. Nothing here stages, commits, or
publishes anything: the candidate bundle is for manual privacy review.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from trace_sanitizer import (
    dumps_jsonl,
    path_variants_for,
    sanitize_records,
    scan_records,
    scan_text,
    summarize,
)

from adapters.claude.parser import parse_claude_jsonl
from security.redact import _redact_text

PROMPT = """You are helping with a small, harmless demo in the current directory. Do these steps in order, one tool call at a time, using exactly the tools named:
1. Read the file inventory.csv.
2. Use the Bash tool to compute the total of the quantity column (for example with awk -F, 'NR>1{s+=$2} END{print s}' inventory.csv).
3. Read the file missing_file.txt (it does not exist; this is an intentional error, do not create it).
4. Read notes.txt, then use the Edit tool to fix the spelling mistake "delibrate" so it reads "deliberate".
5. Use the Write tool to create summary.md containing: the total quantity, and one sentence saying what you fixed.
Finish with a one-sentence summary of what you did.
"""
INVENTORY = "item,quantity,unit_price\nwidget,4,2.50\ngadget,10,1.25\nsprocket,3,4.00\n"
NOTES = (
    "Agent Session Bridge demo notes\n"
    "This file contains a delibrate typo for the agent to fix.\n"
    "All data here is synthetic and harmless.\n"
)
SESSION_MODEL = "claude-sonnet-5"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:  # read-only, streamed
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_records(path: Path) -> list[Any]:
    records: list[Any] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    records.append(line)  # keep position; the sanitizer skeletonizes it
    return records


def default_scan_terms(extra: list[str]) -> list[str]:
    terms = [getpass.getuser(), Path.home().name, socket.gethostname(), "asb-demo", ".claude"]
    for key in ("user.email", "user.name"):
        try:
            value = subprocess.run(
                ["git", "config", "--get", key], capture_output=True, text=True, check=False
            ).stdout.strip()
        except OSError:
            value = ""
        terms.append(value)
    terms += [str(Path.home()), str(Path.home()).replace("\\", "/")]
    return sorted({t for t in terms + extra if len(t) >= 3})


def run_claude_session(root: Path) -> Path:
    """Run the scripted session in the sandbox and return the raw session log path."""
    claude = shutil.which("claude")
    if claude is None:
        raise SystemExit("`claude` was not found on PATH.")
    sandbox = root / "sandbox"
    sandbox.mkdir(parents=True, exist_ok=True)
    (sandbox / "inventory.csv").write_text(INVENTORY, encoding="utf-8", newline="\n")
    (sandbox / "notes.txt").write_text(NOTES, encoding="utf-8", newline="\n")
    for leftover in ("summary.md", "missing_file.txt"):
        (sandbox / leftover).unlink(missing_ok=True)

    session_id = str(uuid.uuid4())
    private = root / "private"
    private.mkdir(parents=True, exist_ok=True)
    (private / "prompt.txt").write_text(PROMPT, encoding="utf-8", newline="\n")
    command = [
        claude, "-p", PROMPT, "--session-id", session_id, "--model", SESSION_MODEL,
        "--tools", "Read,Bash,Edit,Write", "--allowedTools", "Read,Bash,Edit,Write",
        "--strict-mcp-config", "--setting-sources", "project", "--max-budget-usd", "1",
        "--output-format", "json",
    ]  # fmt: skip
    completed = subprocess.run(
        command, cwd=sandbox, capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False
    )
    (private / f"claude_run_{session_id}.json").write_text(completed.stdout, encoding="utf-8")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        result = {}
    if completed.returncode != 0 or result.get("is_error"):
        reason = "authentication" if "authenticate" in str(result.get("result", "")).lower() else "run"
        raise SystemExit(
            f"The Claude Code {reason} failed (exit {completed.returncode}). If this is an "
            "authentication error, run `claude auth login` in your own terminal and retry."
        )
    matches = sorted((Path.home() / ".claude" / "projects").glob(f"*/{session_id}.jsonl"))
    if len(matches) != 1:
        raise SystemExit(f"Expected exactly one session log for {session_id}, found {len(matches)}.")
    return matches[0]


def profile(records: list[Any]) -> dict[str, Any]:
    types: Counter[str] = Counter()
    blocks: Counter[str] = Counter()
    for record in records:
        if not isinstance(record, dict):
            types["(non-object)"] += 1
            continue
        types[str(record.get("type"))] += 1
        message = record.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    blocks[f"{message.get('role')}/{block.get('type')}"] += 1  # type: ignore[union-attr]
    return {
        "records": len(records),
        "record_types": dict(sorted(types.items())),
        "content_block_types": dict(sorted(blocks.items())),
    }


def trajectory_fidelity(lines: str) -> dict[str, Any]:
    trajectory = parse_claude_jsonl(io.StringIO(lines))
    assert trajectory.extra is not None
    fidelity = trajectory.extra["agent_session_bridge"]["fidelity"]
    signature = [
        {
            "source": step.source,
            "timestamp": step.timestamp,
            "model_name": step.model_name,
            "metrics": step.metrics.model_dump() if step.metrics else None,
            "tools": [call.function_name for call in step.tool_calls or []],
            "errors": [
                bool((result.extra or {}).get("is_error"))
                for result in (step.observation.results if step.observation else [])
            ],
            "has_text": bool(step.message),
        }
        for step in trajectory.steps
    ]
    return {"fidelity": fidelity, "step_signature": signature}


def run_cli(args: list[str], log: list[str]) -> str:
    command = [sys.executable, "-m", "cli.main", *args]
    log.append("agent-session " + " ".join(args))
    completed = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", check=False,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
    )  # fmt: skip
    if completed.returncode != 0:
        raise SystemExit(f"agent-session {args[0]} failed: {completed.stderr.strip()[:300]}")
    return completed.stdout


def converter_version() -> str:
    try:
        from importlib.metadata import version

        base = version("atomicdjt-agent-session-bridge")
    except Exception:  # noqa: BLE001 - the version is a label, not a requirement
        base = "unknown"
    try:
        head = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=False,
        ).stdout.strip()  # fmt: skip
        dirty = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True, text=True, check=False,
        ).stdout.strip()  # fmt: skip
    except OSError:
        return base
    return f"{base} (git {head}{', uncommitted changes' if dirty else ''})" if head else base


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--run-claude", action="store_true", help="run the scripted session first")
    source.add_argument("--source", type=Path, help="an existing raw Claude Code session JSONL")
    parser.add_argument("--root", type=Path, default=Path("C:/asb-demo"), help="private root, outside the repo")
    parser.add_argument("--scan-term", action="append", default=[], help="extra string that must not appear")
    args = parser.parse_args()

    root = args.root.resolve()
    if root == REPO_ROOT or REPO_ROOT in root.parents:
        raise SystemExit("The private root must be outside the repository.")
    raw_path = run_claude_session(root) if args.run_claude else args.source.resolve()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = root / "private" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    commands: list[str] = []

    raw_sha_before = sha256_of(raw_path)
    records = read_records(raw_path)
    raw_lines = "".join(
        (json.dumps(r, ensure_ascii=False) if not isinstance(r, str) else r.strip()) + "\n" for r in records
    )
    raw_profile = profile(records)
    cwd = next((r["cwd"] for r in records if isinstance(r, dict) and isinstance(r.get("cwd"), str)), "")
    raw_result = trajectory_fidelity(raw_lines)
    version = next(
        (r["version"] for r in records if isinstance(r, dict) and isinstance(r.get("version"), str)), ""
    )

    sanitized, drops = sanitize_records(records, path_variants=path_variants_for(cwd))
    sanitized_text = dumps_jsonl(sanitized)
    terms = default_scan_terms(args.scan_term)
    findings = scan_records(sanitized, terms, _redact_text)

    staging = run_dir / "staging"
    staging.mkdir()
    sanitized_path = staging / "sanitized.source.jsonl"
    atif_path = staging / "sanitized.atif.json"
    report_path = staging / "report.md"
    manifest_path = staging / "manifest.json"
    write_text(sanitized_path, sanitized_text)
    sanitized_sha = sha256_of(sanitized_path)

    run_cli(["import", "--from", "claude-code", "--source", str(sanitized_path), "--output", str(atif_path)], commands)
    raw_note = (
        f"Source was reduced by an allowlist sanitizer before conversion; raw session SHA-256 "
        f"{raw_sha_before}. The conversion accounts for the sanitized file."
    )
    manifest = {
        "source_sha256": sanitized_sha,
        "claude_code_version": version,
        "converter_version": converter_version(),
        "capture_time": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": raw_note,
    }
    if not version:
        manifest.pop("claude_code_version")
    write_text(manifest_path, json.dumps(manifest, indent=2) + "\n")
    run_cli(["explain", str(atif_path), "--manifest", str(manifest_path), "--output", str(report_path)], commands)

    # The two hashes are deliberate; mask them so they are not reported as token-like runs.
    def _masked(path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        return text.replace(raw_sha_before, "<raw-sha256>").replace(sanitized_sha, "<sanitized-sha256>")

    findings += scan_text("atif", _masked(atif_path), terms, _redact_text)
    findings += scan_text("report", _masked(report_path), terms, _redact_text)
    findings += scan_text("manifest", _masked(manifest_path), terms, _redact_text)
    scan = summarize(findings)

    sanitized_result = trajectory_fidelity(sanitized_text)
    volatile = {"transformations"}
    fidelity_equal = {
        key: raw_result["fidelity"][key] == sanitized_result["fidelity"][key]
        for key in raw_result["fidelity"]
        if key not in volatile
    }
    equivalence = {
        "fidelity_counters_equal": all(fidelity_equal.values()),
        "per_counter": fidelity_equal,
        "transformations_equal": raw_result["fidelity"]["transformations"]
        == sanitized_result["fidelity"]["transformations"],
        "step_structure_equal": raw_result["step_signature"] == sanitized_result["step_signature"],
        "raw_fidelity": raw_result["fidelity"],
    }
    raw_sha_after = sha256_of(raw_path)
    checks = {
        "raw_unchanged_during_run": raw_sha_before == raw_sha_after,
        "raw_sha256": raw_sha_before,
        "raw_path": "(recorded in the private run notes only)",
        "scan_status": scan["status"],
        "equivalence_ok": equivalence["fidelity_counters_equal"] and equivalence["step_structure_equal"],
    }

    write_text(run_dir / "scan_results.json", json.dumps(scan, indent=2) + "\n")
    write_text(run_dir / "raw_profile.json", json.dumps(raw_profile, indent=2) + "\n")
    write_text(run_dir / "equivalence.json", json.dumps(equivalence, indent=2) + "\n")
    write_text(run_dir / "field_drop_list.json", json.dumps(drops.as_dict(), indent=2) + "\n")
    write_text(run_dir / "private_run_notes.json", json.dumps({**checks, "raw_path": str(raw_path), "commands": commands}, indent=2) + "\n")

    candidate = run_dir / "candidate"
    if scan["status"] == "PASS":
        staging.rename(candidate)
        write_text(
            run_dir / "SHA256SUMS.txt",
            "".join(f"{sha256_of(p)}  candidate/{p.name}\n" for p in sorted(candidate.iterdir())),
        )
    else:
        shutil.rmtree(staging)

    print(f"run directory : {run_dir}")
    print(f"raw sha256    : {raw_sha_before} (unchanged during run: {checks['raw_unchanged_during_run']})")
    print(f"raw records   : {raw_profile['records']}  types: {raw_profile['record_types']}")
    print(f"scan          : {scan['status']}  fail={scan['fail_count']}  review={scan['review_count']}")
    print(f"equivalence   : counters={equivalence['fidelity_counters_equal']} steps={equivalence['step_structure_equal']}")
    print(f"candidate     : {candidate if scan['status'] == 'PASS' else 'WITHHELD (scan failed)'}")
    if scan["status"] != "PASS" or not checks["equivalence_ok"] or not checks["raw_unchanged_during_run"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
