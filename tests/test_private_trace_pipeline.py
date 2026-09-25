"""The private-trace tooling: sanitization, the scan gate, and the end-to-end demo command.

All data is synthetic. The canary strings stand in for things that must never survive
sanitization; the tests fail if any of them reaches a candidate file.
"""

import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path("tools").resolve()))

from trace_sanitizer import (
    DROPPED,
    dumps_jsonl,
    path_variants_for,
    sanitize_records,
    scan_records,
    scan_text,
    summarize,
)

from adapters.claude.parser import parse_claude_jsonl
from security.redact import _redact_text

SANDBOX = "C:\\demo-sandbox\\work"
CANARY_ATTACHMENT = "CANARY-attachment-text"
CANARY_PROMPT_ECHO = "CANARY-prompt-echo"
CANARY_TOOL_STRUCT = "CANARY-tool-use-result"
CANARY_SIGNATURE = "CANARY-signature"
CANARY_REQUEST = "CANARY-request-id"
CANARY_REASONING = "CANARY-reasoning-text"
CANARY_USAGE_EXTRA = "CANARY-usage-extra"
CANARIES = [
    CANARY_ATTACHMENT, CANARY_PROMPT_ECHO, CANARY_TOOL_STRUCT, CANARY_SIGNATURE,
    CANARY_REQUEST, CANARY_REASONING, CANARY_USAGE_EXTRA,
]  # fmt: skip
USAGE = {
    "input_tokens": 3,
    "cache_read_input_tokens": 100,
    "cache_creation_input_tokens": 20,
    "output_tokens": 9,
    "service_tier": CANARY_USAGE_EXTRA,
}


def _common(uuid: str) -> dict[str, Any]:
    return {
        "uuid": uuid,
        "parentUuid": "11111111-2222-3333-4444-555555555555",
        "isSidechain": False,
        "userType": "external",
        "entrypoint": "cli",
        "cwd": SANDBOX,
        "sessionId": "0f8135fa-42b6-4d55-a594-0fcbb860dc67",
        "version": "9.9.9",
        "gitBranch": "HEAD",
    }


def _assistant(blocks: list[dict[str, Any]], message_id: str, stamp: str) -> dict[str, Any]:
    return {
        "type": "assistant",
        "timestamp": stamp,
        "requestId": CANARY_REQUEST,
        "message": {
            "id": message_id,
            "role": "assistant",
            "type": "message",
            "model": "claude-test-1",
            "stop_reason": "tool_use",
            "content": blocks,
            "usage": USAGE,
        },
        **_common("aaaaaaaa-0000-0000-0000-00000000000" + message_id[-1]),
    }


def _tool_result(call_id: str, content: str, stamp: str, *, error: bool = False) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "tool_result", "tool_use_id": call_id, "content": content}
    if error:
        block["is_error"] = True
    return {
        "type": "user",
        "timestamp": stamp,
        "toolUseResult": CANARY_TOOL_STRUCT,
        "message": {"role": "user", "content": [block]},
        **_common("bbbbbbbb-0000-0000-0000-000000000001"),
    }


def raw_session(*, leak: str | None = None) -> list[dict[str, Any]]:
    """A synthetic session with the record shapes real Claude Code 2.1.x logs contain."""
    read_input = {"file_path": SANDBOX + "\\data.csv"}
    return [
        {"type": "queue-operation", "operation": "enqueue", "content": CANARY_PROMPT_ECHO},
        {"type": "file-history-snapshot", "snapshot": {"trackedFileBackups": {}}},
        {
            "type": "user",
            "timestamp": "2026-01-01T00:00:00Z",
            "promptId": "p1",
            "message": {"role": "user", "content": "Read data.csv, then read missing.txt."},
            **_common("cccccccc-0000-0000-0000-000000000001"),
        },
        {"type": "attachment", "attachment": {"type": "date", "content": CANARY_ATTACHMENT}},
        _assistant(
            [{"type": "thinking", "thinking": "", "signature": CANARY_SIGNATURE}], "msg_01A", "2026-01-01T00:00:01Z"
        ),
        _assistant(
            [
                {"type": "tool_use", "id": "toolu_01A", "name": "Read", "input": read_input},
                {"type": "tool_use", "id": "toolu_01B", "name": "Read", "input": {"file_path": "/c/demo-sandbox/work/missing.txt"}},
            ],
            "msg_01A",
            "2026-01-01T00:00:02Z",
        ),
        _tool_result("toolu_01A", "a,b\n1,2 in " + SANDBOX + (leak or ""), "2026-01-01T00:00:03Z"),
        _tool_result("toolu_01B", "File does not exist.", "2026-01-01T00:00:04Z", error=True),
        _assistant(
            [
                {"type": "thinking", "thinking": CANARY_REASONING, "signature": CANARY_SIGNATURE},
                {"type": "text", "text": "Done: one file read, one missing."},
            ],
            "msg_01B",
            "2026-01-01T00:00:05Z",
        ),
        {"type": "last-prompt", "lastPrompt": CANARY_PROMPT_ECHO, "leafUuid": "x"},
        {"type": "system", "subtype": "turn_duration", "durationMs": 42},
    ]


def _fidelity(lines: str) -> dict[str, Any]:
    trajectory = parse_claude_jsonl(io.StringIO(lines))
    assert trajectory.extra is not None
    fidelity = dict(trajectory.extra["agent_session_bridge"]["fidelity"])
    return fidelity


def _sanitized() -> tuple[list[dict[str, Any]], Any]:
    return sanitize_records(raw_session(), path_variants=path_variants_for(SANDBOX))


def test_no_dropped_content_survives_and_only_type_skeletons_remain_for_bookkeeping():
    records, _ = _sanitized()
    text = dumps_jsonl(records)

    for canary in CANARIES:
        assert canary not in text
    skeletons = [r for r in records if r.get("type") not in {"user", "assistant"}]
    assert skeletons == [
        {"type": "queue-operation"},
        {"type": "file-history-snapshot"},
        {"type": "attachment"},
        {"type": "last-prompt"},
        {"type": "system", "subtype": "turn_duration"},
    ]


def test_fields_outside_the_allowlist_are_replaced_and_counted():
    records, report = _sanitized()
    user = records[2]

    assert user["uuid"] == DROPPED and user["parentUuid"] == DROPPED and user["promptId"] == DROPPED
    assert user["sessionId"] == "session-demo"
    assert user["cwd"] == "/workspace"
    assert report.fields_replaced["uuid"] >= 1
    assert report.fields_replaced["message.stop_reason"] == 3
    assert report.fields_replaced["toolUseResult"] == 2
    assert records[4]["message"]["usage"] == {
        "input_tokens": 3, "cache_read_input_tokens": 100,
        "cache_creation_input_tokens": 20, "output_tokens": 9,
    }  # fmt: skip


def test_thinking_keeps_only_whether_it_held_text():
    records, _ = _sanitized()
    empty, with_text = records[4]["message"]["content"][0], records[8]["message"]["content"][0]

    assert empty == {"type": "thinking", "thinking": ""}
    assert with_text == {"type": "thinking", "thinking": DROPPED}


def test_identifiers_are_pseudonymized_consistently():
    records, report = _sanitized()
    first, second = records[4]["message"], records[5]["message"]
    call_a = records[5]["message"]["content"][0]["id"]
    result_a = records[6]["message"]["content"][0]["tool_use_id"]

    assert first["id"] == second["id"] == "message-0001"
    assert records[8]["message"]["id"] == "message-0002"
    assert call_a == result_a == "tool-call-0001"
    assert "toolu_01A" not in dumps_jsonl(records) and "msg_01A" not in dumps_jsonl(records)
    assert report.identifiers_pseudonymized["message"] == 2
    assert report.identifiers_pseudonymized["tool_call"] == 2


def test_every_spelling_of_the_sandbox_path_is_replaced():
    records, report = _sanitized()
    text = dumps_jsonl(records)

    assert "demo-sandbox" not in text
    assert records[5]["message"]["content"][0]["input"] == {"file_path": "/workspace\\data.csv"}
    assert records[5]["message"]["content"][1]["input"] == {"file_path": "/workspace/missing.txt"}
    assert report.path_substitutions == 3


def test_sanitized_log_has_the_same_fidelity_accounting_as_the_raw_log():
    raw = "".join(json.dumps(r) + "\n" for r in raw_session())
    records, _ = _sanitized()
    sanitized = dumps_jsonl(records)
    raw_fidelity, sanitized_fidelity = _fidelity(raw), _fidelity(sanitized)

    assert raw_fidelity == sanitized_fidelity
    assert raw_fidelity["unsupported_source_records"] == 5
    assert raw_fidelity["duplicate_usage_records"] == 1
    assert {e["type"]: e["with_content"] for e in raw_fidelity["unsupported_block_types"]} == {"thinking": 1}


def test_scan_fails_on_forbidden_terms_identifiers_and_secret_shapes_without_echoing_them():
    secret = "sk-abcdefghijklmnopqrstuvwxyz"
    records = [
        {"type": "user", "message": {"content": "mail me at jane.doe@example.com"}},
        {"type": "user", "message": {"content": "C:\\Users\\Someone\\file and 0f8135fa-42b6-4d55-a594-0fcbb860dc67"}},
        {"type": "user", "message": {"content": f"key {secret}"}},
    ]
    findings = scan_records(records, ["Users\\Someone"], _redact_text)
    summary = summarize(findings)
    categories = {f.category for f in findings if f.severity == "FAIL"}

    assert summary["status"] == "FAIL"
    assert {"email", "uuid", "forbidden_term"} <= categories
    assert any(c.startswith("secret_shape") for c in categories)
    assert secret not in json.dumps(summary) and "jane.doe" not in json.dumps(summary)


def test_scan_flags_urls_and_foreign_paths_for_review_but_passes_workspace_paths():
    review = scan_text("x", "see https://example.com/a and /home/u/x and C:\\Temp\\y", [], _redact_text)
    assert {f.category for f in review} == {"url", "absolute_path"}
    assert all(f.severity == "REVIEW" for f in review)
    assert scan_text("x", "open /workspace/notes.txt", [], _redact_text) == []
    assert summarize(review)["status"] == "PASS"
    assert "not a clearance" in summarize(review)["meaning"]


def _run_demo(source: Path, root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "tools/private_demo.py", "--source", str(source), "--root", str(root), *extra],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )  # fmt: skip


def _write_raw(tmp_path: Path, **kwargs: Any) -> Path:
    raw = tmp_path / "raw_session.jsonl"
    raw.write_text("".join(json.dumps(r) + "\n" for r in raw_session(**kwargs)), encoding="utf-8")
    return raw


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_demo_command_produces_a_reviewable_candidate_and_leaves_the_raw_log_alone(tmp_path: Path):
    raw = _write_raw(tmp_path)
    before = _sha(raw)
    root = tmp_path / "private-root"
    outcome = _run_demo(raw, root)

    assert outcome.returncode == 0, outcome.stdout + outcome.stderr
    assert _sha(raw) == before
    (run_dir,) = (root / "private" / "runs").iterdir()
    candidate = run_dir / "candidate"
    assert sorted(p.name for p in candidate.iterdir()) == [
        "manifest.json", "report.md", "sanitized.atif.json", "sanitized.source.jsonl",
    ]  # fmt: skip
    assert {p.name for p in run_dir.iterdir()} >= {
        "scan_results.json", "field_drop_list.json", "equivalence.json", "raw_profile.json", "SHA256SUMS.txt",
    }
    for path in candidate.iterdir():
        text = path.read_text(encoding="utf-8")
        assert not any(canary in text for canary in CANARIES), path.name
        assert "demo-sandbox" not in text
    equivalence = json.loads((run_dir / "equivalence.json").read_text(encoding="utf-8"))
    assert equivalence["fidelity_counters_equal"] and equivalence["step_structure_equal"]
    report = (candidate / "report.md").read_text(encoding="utf-8")
    assert "- Tool calls: 2 — 1 with a result, 1 with an error result, 0 with no result recorded" in report
    assert "### Supplied by the manifest (not verified by this report)" in report
    manifest = json.loads((candidate / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_sha256"] == _sha(candidate / "sanitized.source.jsonl")
    assert before in manifest["note"]
    sums = (run_dir / "SHA256SUMS.txt").read_text(encoding="utf-8")
    assert _sha(candidate / "report.md") in sums


def test_demo_command_withholds_everything_when_the_scan_fails(tmp_path: Path):
    raw = _write_raw(tmp_path, leak=" owner=canary-username")
    root = tmp_path / "private-root"
    outcome = _run_demo(raw, root, "--scan-term", "canary-username")

    assert outcome.returncode == 2
    assert "WITHHELD" in outcome.stdout
    (run_dir,) = (root / "private" / "runs").iterdir()
    assert not (run_dir / "candidate").exists() and not (run_dir / "staging").exists()
    scan = json.loads((run_dir / "scan_results.json").read_text(encoding="utf-8"))
    assert scan["status"] == "FAIL"
    assert "canary-username" not in json.dumps(scan)


def test_demo_command_refuses_a_private_root_inside_the_repository(tmp_path: Path):
    outcome = _run_demo(_write_raw(tmp_path), Path("work-inside-repo"))
    assert outcome.returncode != 0
    assert "outside the repository" in outcome.stderr
    assert not Path("work-inside-repo").exists()


@pytest.mark.parametrize("bad", ["not json at all", "[1, 2, 3]"])
def test_malformed_lines_become_type_only_skeletons(bad: str):
    records, report = sanitize_records([bad, {"no_type": "secret-value"}], path_variants=[])

    assert records == [{"type": "unknown"}, {}]
    assert "secret-value" not in dumps_jsonl(records)
    assert sum(report.records_reduced_to_skeleton.values()) == 2
