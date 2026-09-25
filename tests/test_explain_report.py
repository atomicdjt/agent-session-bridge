"""The Markdown report: determinism, provenance honesty, correlation, and loss accounting.

All trace content is synthetic.
"""

import copy
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from atif import Trajectory

from adapters.claude.parser import parse_claude_jsonl
from cli.main import main
from explain import ManifestError, load_manifest, render_report
from security.redact import redact_trajectory

USAGE = {
    "input_tokens": 3,
    "cache_read_input_tokens": 1000,
    "cache_creation_input_tokens": 200,
    "output_tokens": 40,
}
SHA = "ab" * 32


def _records() -> list[dict[str, Any]]:
    def assistant(blocks: list[dict[str, Any]], message_id: str, stamp: str) -> dict[str, Any]:
        return {
            "type": "assistant",
            "timestamp": stamp,
            "sessionId": "demo-session",
            "version": "9.9.9",
            "cwd": "C:\\demo\\sandbox",
            "message": {
                "role": "assistant",
                "id": message_id,
                "model": "claude-test-1",
                "content": blocks,
                "usage": USAGE,
                "stop_reason": "tool_use",
            },
        }

    def result(call_id: str, content: str, stamp: str, error: bool = False) -> dict[str, Any]:
        block: dict[str, Any] = {"type": "tool_result", "tool_use_id": call_id, "content": content}
        if error:
            block["is_error"] = True
        return {
            "type": "user",
            "timestamp": stamp,
            "message": {"role": "user", "content": [block]},
            "toolUseResult": "structured",
        }

    return [
        {"type": "file-history-snapshot", "snapshot": {}},
        {
            "type": "user",
            "timestamp": "2026-01-01T00:00:00Z",
            "sessionId": "demo-session",
            "version": "9.9.9",
            "message": {"role": "user", "content": "Do the demo."},
        },
        {"type": "attachment", "attachment": {"type": "date"}},
        assistant([{"type": "thinking", "thinking": "", "signature": "x"}], "m1", "2026-01-01T00:00:01Z"),
        assistant(
            [
                {"type": "text", "text": "Reading two files."},
                {"type": "tool_use", "id": "c1", "name": "Read", "input": {"file_path": "a.csv"}},
                {"type": "tool_use", "id": "c2", "name": "Read", "input": {"file_path": "missing.txt"}},
                {"type": "tool_use", "id": "c3", "name": "Bash", "input": {"command": "echo hi"}},
            ],
            "m1",
            "2026-01-01T00:00:02Z",
        ),
        result("c1", "a,b\n1,2", "2026-01-01T00:00:03Z"),
        result("c2", "File does not exist.", "2026-01-01T00:00:04Z", error=True),
        {"type": "system", "subtype": "turn_duration", "durationMs": 12},
    ]


def _trajectory(records: list[dict[str, Any]] | None = None) -> Trajectory:
    lines = "\n".join(json.dumps(r) for r in (records or _records()))
    return parse_claude_jsonl(io.StringIO(lines))


def _report(records: list[dict[str, Any]] | None = None, **kwargs: Any) -> str:
    return render_report(_trajectory(records), **kwargs)


def test_report_is_deterministic_for_the_same_document():
    trajectory = _trajectory()
    document = json.loads(trajectory.model_dump_json())
    first = render_report(Trajectory.model_validate(document))
    second = render_report(Trajectory.model_validate(copy.deepcopy(document)))

    assert first == second
    assert first.endswith("\n") and not first.endswith("\n\n")


def test_provenance_shows_only_what_the_document_records():
    report = _report()

    assert "`demo-session`" in report
    assert "`claude-code 9.9.9`" in report
    assert "`claude-code-jsonl`" in report
    assert "Conversion timestamp" in report
    assert "Supplied by the manifest" not in report
    # Source-level facts ATIF does not carry are listed as unavailable, not shown.
    assert "Source file SHA-256, Converter version, Capture time" in report
    assert SHA not in report


def test_manifest_facts_are_labelled_and_no_longer_listed_as_missing():
    manifest = {
        "source_sha256": SHA,
        "converter_version": "0.3.0+demo",
        "capture_time": "2026-01-02T03:04:05Z",
        "claude_code_version": "9.9.9",
    }
    report = _report(manifest=manifest)

    assert "### Supplied by the manifest (not verified by this report)" in report
    assert SHA in report and "0.3.0+demo" in report
    assert "### Not available" not in report
    assert "differs from the version recorded" not in report


def test_manifest_partially_supplied_keeps_the_rest_listed_as_unavailable():
    report = _report(manifest={"source_sha256": SHA})
    assert "no manifest supplied them: Converter version, Capture time" in report


def test_manifest_claude_code_version_conflict_is_reported_not_resolved():
    report = _report(manifest={"claude_code_version": "1.0.0"})
    assert "differs from the version recorded in the ATIF document (`9.9.9`)" in report


@pytest.mark.parametrize(
    "manifest",
    [
        {"unknown_field": "x"},
        {"source_sha256": "not-a-hash"},
        {"capture_time": "yesterday"},
        {"note": ""},
        {"note": 5},
    ],
)
def test_invalid_manifests_are_rejected(manifest: dict[str, Any]):
    with pytest.raises(ManifestError):
        _report(manifest=manifest)


def test_load_manifest_reads_a_json_file(tmp_path: Path):
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"note": "hello"}), encoding="utf-8")
    assert load_manifest(path) == {"note": "hello"}
    path.write_text("[1]", encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(path)
    with pytest.raises(ManifestError):
        load_manifest(tmp_path / "absent.json")


def test_tool_calls_are_correlated_with_results_including_the_error_and_the_gap():
    report = _report()

    table = report.split("## Tool calls and results")[1].split("\n## ")[0]
    rows = [line for line in table.splitlines() if line.startswith("| ")][2:]
    assert rows == [
        "| 3 | `Read` | `c1` | result |",
        "| 3 | `Read` | `c2` | error |",
        "| 3 | `Bash` | `c3` | no result |",
    ]
    assert "- Tool calls: 3 — 1 with a result, 1 with an error result, 1 with no result recorded" in report
    assert "**Result (error):**" in report
    assert "File does not exist." in report
    assert "**Result:** none recorded for this call ID." in report


def test_thinking_only_step_is_shown_as_empty_and_linked_to_its_response():
    report = _report()

    assert "_No message text and no tool calls in this step._" in report
    assert "shares that response with step 3" in report


def test_loss_section_separates_bookkeeping_from_possible_content_loss():
    report = _report()
    section = report.split("## What this conversion could not preserve")[1]

    assert "**1 record(s) that may hold content** not converted: `attachment` ×1" in section
    assert "**2 session-metadata record(s)** not converted" in section
    assert "`file-history-snapshot` ×1" in section and "`system/turn_duration` ×1" in section
    assert "each held only an opaque signature" in section
    assert "`toolUseResult` (2)" in section and "`message.stop_reason` (2)" in section
    assert "Tool-result timestamps not represented: 2." in section
    assert "### Limits of this section" in section


def test_thinking_block_with_text_is_reported_as_content_loss():
    records = _records()
    records[3]["message"]["content"][0]["thinking"] = "visible reasoning"
    section = _report(records).split("## What this conversion could not preserve")[1]

    assert "1 carried content that is absent from the trajectory" in section
    assert "opaque signature" not in section


def test_consistency_checks_compare_the_report_with_the_document():
    trajectory = _trajectory()
    assert "the fidelity report (3) matches the document (3)" in render_report(trajectory)

    assert trajectory.extra is not None
    trajectory.extra["agent_session_bridge"]["fidelity"]["tool_calls_preserved"] = 5
    report = render_report(trajectory)
    assert "**mismatch** — the fidelity report says 5, the document contains 3" in report


def test_document_from_an_older_converter_is_not_over_interpreted():
    document = json.loads(Path("fixtures/conformance/degraded-fidelity.atif.json").read_text(encoding="utf-8"))
    report = render_report(Trajectory.model_validate(document))
    section = report.split("## What this conversion could not preserve")[1]

    assert "Source records not converted: 1." in section
    assert "Content blocks not converted: 2." in section
    assert "did not report which kinds" in section
    assert "did not report their types" in section
    assert "### Transformations recorded by the converter" in section
    assert "- Dropped provider_private_annotation because no portable ATIF field exists." in section
    assert "does not judge whether each one lost information" in section
    assert "Changed but not lost" not in section


def test_document_without_asb_extension_says_it_cannot_tell():
    document = json.loads(Path("fixtures/claude_sample.atif.json").read_text(encoding="utf-8"))
    document.pop("extra", None)
    report = render_report(Trajectory.model_validate(document))

    assert "no `extra.agent_session_bridge.provenance`" in report
    assert "cannot be determined from it. That is not evidence that nothing was lost." in report


def test_untrusted_text_cannot_become_markdown_structure():
    records = _records()
    records[5]["message"]["content"][0]["content"] = "```\n# Injected heading\n```\n| a | b |"
    records[4]["message"]["content"][2]["name"] = "Bash`|evil"
    report = _report(records)

    assert "````text\n```\n# Injected heading\n```\n| a | b |\n````" in report
    assert "\n# Injected heading" not in report.replace("\n```\n# Injected heading", "")
    assert "| `` Bash`|evil `` |" not in report  # table cell must not use a raw pipe
    assert "Bash`\\|evil" in report


def test_long_content_is_truncated_with_a_note_unless_disabled():
    records = _records()
    records[5]["message"]["content"][0]["content"] = "x" * 50
    short = _report(records, max_chars=10)
    full = _report(records, max_chars=0)

    assert "_Truncated: first 10 of 50 characters shown." in short
    assert "x" * 50 not in short
    assert "x" * 50 in full and "Truncated" not in full


def test_token_usage_uses_atif_semantics_and_shows_no_cost():
    report = _report()
    # One API response (m1) spans two records, but its usage is counted once.
    assert "Summed over 1 step that carry metrics (tokens):" in report
    assert "Prompt tokens, including cached: 1203" in report
    assert "Of which cached: 1000" in report
    assert "Completion tokens: 40" in report
    assert "written to the prompt cache: 200" in report
    assert "No monetary cost is shown" in report


def test_redaction_markers_are_reported_from_the_document_only():
    records = _records()
    records[5]["message"]["content"][0]["content"] = "api_key = sk-abcdefghijklmnop"
    report = render_report(redact_trajectory(_trajectory(records)))
    assert "Redaction markers in message, argument, or result text" in report
    assert "not recoverable from this document" in report


def test_cli_explain_writes_a_report_and_reports_failures(tmp_path: Path, monkeypatch, capsys):
    atif = tmp_path / "t.atif.json"
    atif.write_text(_trajectory().model_dump_json(), encoding="utf-8")
    out = tmp_path / "sub" / "report.md"

    monkeypatch.setattr(sys, "argv", ["agent-session", "explain", str(atif), "--output", str(out)])
    main()
    assert out.read_text(encoding="utf-8") == render_report(_trajectory_from(atif))
    assert b"\r\n" not in out.read_bytes()

    monkeypatch.setattr(sys, "argv", ["agent-session", "explain", str(tmp_path / "missing.json")])
    with pytest.raises(SystemExit) as failure:
        main()
    assert failure.value.code == 1
    assert "Cannot explain" in capsys.readouterr().err

    bad_manifest = tmp_path / "m.json"
    bad_manifest.write_text('{"bogus": "x"}', encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv", ["agent-session", "explain", str(atif), "--manifest", str(bad_manifest)]
    )
    with pytest.raises(SystemExit):
        main()
    assert "unknown manifest field" in capsys.readouterr().err


def _trajectory_from(path: Path) -> Trajectory:
    return Trajectory.model_validate(json.loads(path.read_text(encoding="utf-8")))
