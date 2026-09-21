"""Regression tests for timestamp fidelity and unknown-structure handling in the Claude parser."""

from __future__ import annotations

import copy
import json
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from atif import Trajectory

from adapters.claude.parser import parse_claude_jsonl
from interoperability.verifier import (
    _read_source,
    _unsupported_source_record_descriptors,
    verify_files,
)
from security.redact import redact_trajectory

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "fixtures" / "interoperability"
SOURCE = FIXTURE_DIR / "claude-comprehensive.source.jsonl"
ORACLE = FIXTURE_DIR / "expected-semantics.json"

CALL = {"type": "tool_use", "id": "call-1", "name": "inspect", "input": {}}


def _parse(*records: dict[str, Any]) -> Trajectory:
    return parse_claude_jsonl(StringIO("\n".join(json.dumps(record) for record in records)))


def _assistant(content: Any, timestamp: Any = "2026-01-01T00:00:01Z") -> dict[str, Any]:
    record: dict[str, Any] = {"type": "assistant", "message": {"role": "assistant", "content": content}}
    if timestamp is not None:
        record["timestamp"] = timestamp
    return record


def _user(content: Any, timestamp: Any = "2026-01-01T00:00:02Z") -> dict[str, Any]:
    record: dict[str, Any] = {"type": "user", "message": {"role": "user", "content": content}}
    if timestamp is not None:
        record["timestamp"] = timestamp
    return record


def _fidelity(trajectory: Trajectory) -> dict[str, Any]:
    assert trajectory.extra is not None
    return trajectory.extra["agent_session_bridge"]["fidelity"]


def test_tool_result_timestamps_are_reported_and_never_copied_onto_the_call_step():
    """ATIF v1.7 has no ObservationResult timestamp: report the loss, do not relocate it."""
    trajectory = _parse(
        _assistant([CALL], "2026-01-01T00:00:01Z"),
        _user([{"type": "tool_result", "tool_use_id": "call-1", "content": "ok"}], "2026-01-01T00:00:09Z"),
    )

    assert len(trajectory.steps) == 1
    assert trajectory.steps[0].timestamp == "2026-01-01T00:00:01Z"
    assert "2026-01-01T00:00:09Z" not in trajectory.model_dump_json()
    assert _fidelity(trajectory)["omitted_tool_result_timestamps"] == 1
    assert _fidelity(trajectory)["invalid_source_timestamps"] == 0


def test_untimestamped_tool_result_and_orphan_are_not_counted_as_timestamp_loss():
    trajectory = _parse(
        _assistant([CALL]),
        _user([{"type": "tool_result", "tool_use_id": "call-1", "content": "ok"}], None),
        _user([{"type": "tool_result", "tool_use_id": "missing", "content": "x"}], "2026-01-01T00:00:03Z"),
    )

    fidelity = _fidelity(trajectory)
    assert fidelity["omitted_tool_result_timestamps"] == 0
    assert fidelity["orphaned_tool_results"] == 1


@pytest.mark.parametrize("bad", ["not-a-time", 12345, {"a": 1}, ["2026-01-01T00:00:00Z"]])
def test_unrepresentable_source_timestamp_is_omitted_and_counted_not_fatal(bad):
    trajectory = _parse(_user("hello", bad), _user("world", "2026-01-01T00:00:05Z"))

    assert [step.timestamp for step in trajectory.steps] == [None, "2026-01-01T00:00:05Z"]
    assert [step.message for step in trajectory.steps] == ["hello", "world"]
    assert _fidelity(trajectory)["invalid_source_timestamps"] == 1


def test_missing_timestamp_is_not_fabricated_or_counted_as_invalid():
    trajectory = _parse(_user("hello", None))

    assert trajectory.steps[0].timestamp is None
    assert _fidelity(trajectory)["invalid_source_timestamps"] == 0


@pytest.mark.parametrize("text", [None, 5, {"a": 1}, ["x"]])
def test_text_block_without_string_text_is_unsupported_not_stringified(text):
    trajectory = _parse(_user([{"type": "text", "text": text}, {"type": "text", "text": "kept"}]))

    assert trajectory.steps[0].message == "kept"
    assert _fidelity(trajectory)["unsupported_source_blocks"] == 1


@pytest.mark.parametrize("name", [None, 5, "", "   "])
def test_tool_use_without_a_string_name_is_unsupported_not_stringified(name):
    block = {"type": "tool_use", "id": "call-1", "name": name, "input": {}}
    trajectory = _parse(_assistant([block]))

    assert not trajectory.steps[0].tool_calls
    fidelity = _fidelity(trajectory)
    assert fidelity["unsupported_source_blocks"] == 1
    assert fidelity["tool_calls_preserved"] == 0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(True, True), ("false", "false"), (1, 1), (False, None), (None, None), (0, None)],
)
def test_is_error_is_preserved_verbatim_and_never_coerced_to_true(raw, expected):
    block = {"type": "tool_result", "tool_use_id": "call-1", "content": "x", "is_error": raw}
    trajectory = _parse(_assistant([CALL]), _user([block]))

    result = trajectory.steps[0].observation.results[0]
    assert (result.extra or {}).get("is_error") == expected


@pytest.mark.parametrize(
    "block",
    [
        {"type": "thinking", "thinking": "private reasoning"},
        {"type": "redacted_thinking", "data": "opaque"},
        {"type": "server_tool_use", "id": "srv-1", "name": "web_search", "input": {}},
        {"type": "web_search_tool_result", "tool_use_id": "srv-1", "content": []},
        {"type": "document", "source": {"type": "text", "data": "x"}},
        {"type": "some_future_block", "text": "looks like text but is not a text block"},
        "bare string block",
        None,
    ],
)
def test_unknown_or_unsupported_blocks_never_become_text_or_calls(block):
    trajectory = _parse(_assistant([block, {"type": "text", "text": "visible"}]))

    step = trajectory.steps[0]
    assert step.message == "visible"
    assert not step.tool_calls
    assert _fidelity(trajectory)["unsupported_source_blocks"] == 1


def test_mixed_supported_and_unsupported_blocks_keep_only_supported_semantics():
    trajectory = _parse(
        _assistant([{"type": "thinking", "thinking": "x"}, {"type": "text", "text": "hi"}, CALL]),
        _user(
            [
                {"type": "tool_result", "tool_use_id": "call-1", "content": "ok"},
                {"type": "image", "source": {"type": "base64", "data": "AAAA"}},
                {"type": "text", "text": "thanks"},
            ]
        ),
    )

    assert [step.source for step in trajectory.steps] == ["agent", "user"]
    assert trajectory.steps[0].message == "hi"
    assert trajectory.steps[0].observation.results[0].content == "ok"
    assert trajectory.steps[1].message == "thanks"
    fidelity = _fidelity(trajectory)
    assert fidelity["unsupported_source_blocks"] == 2
    assert fidelity["observation_results_preserved"] == 1


def test_source_reader_uses_parser_line_boundaries_for_unicode_line_separators(tmp_path: Path):
    """U+2028/U+0085 are legal inside JSON strings and must not split a source record."""
    separators = "".join(chr(code) for code in (0x2028, 0x85, 0x2029))
    lines = [
        json.dumps(_user("a" + separators + "b"), ensure_ascii=False),
        json.dumps({"type": "progress", "timestamp": "2026-01-01T00:00:03Z"}),
    ]
    path = tmp_path / "source.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    records = _read_source(path)

    assert len(records) == 2
    assert _unsupported_source_record_descriptors(records) == [{"record": 2, "type": "progress"}]
    with path.open(encoding="utf-8") as source_file:
        fidelity = _fidelity(parse_claude_jsonl(source_file))
    assert fidelity["unsupported_source_records"] == 1


def _canonical_document() -> dict[str, Any]:
    with SOURCE.open(encoding="utf-8") as source_file:
        return redact_trajectory(parse_claude_jsonl(source_file)).to_json_dict()


def _finding(report: dict[str, Any], name: str) -> dict[str, str]:
    return next(finding for finding in report["findings"] if finding["name"] == name)


def test_verifier_reports_result_timestamp_loss_from_source_facts(tmp_path: Path):
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(_canonical_document()), encoding="utf-8")

    report = verify_files(SOURCE, path, ORACLE)

    finding = _finding(report, "tool_result_timestamps")
    assert finding["state"] == "OMITTED"
    assert "2 source tool-result timestamp(s)" in finding["detail"]


def test_verifier_flags_asb_fidelity_that_understates_result_timestamp_loss(tmp_path: Path):
    document = copy.deepcopy(_canonical_document())
    document["extra"]["agent_session_bridge"]["fidelity"]["omitted_tool_result_timestamps"] = 0
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    report = verify_files(SOURCE, path, ORACLE)

    assert _finding(report, "tool_result_timestamps")["state"] == "CONFLICT"
    assert report["summary"]["passed"] is False


def test_verifier_result_timestamp_finding_is_not_applicable_without_timestamped_results(tmp_path: Path):
    source = tmp_path / "source.jsonl"
    stripped = []
    for line in SOURCE.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if any(
            isinstance(block, dict) and block.get("type") == "tool_result"
            for block in (record.get("message") or {}).get("content", [])
            if isinstance(record.get("message"), dict) and isinstance(record["message"].get("content"), list)
        ):
            record.pop("timestamp")
        stripped.append(json.dumps(record))
    source.write_text("\n".join(stripped) + "\n", encoding="utf-8")
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(_canonical_document()), encoding="utf-8")

    report = verify_files(source, path, ORACLE, implementation="peer")

    assert _finding(report, "tool_result_timestamps")["state"] == "NOT_APPLICABLE"
