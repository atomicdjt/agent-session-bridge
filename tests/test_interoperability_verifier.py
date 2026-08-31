from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from atif import Trajectory

from adapters.claude.parser import parse_claude_jsonl
from interoperability.verifier import _read_source, verify_files
from security.redact import redact_trajectory

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "fixtures" / "interoperability"
SOURCE = FIXTURE_DIR / "claude-comprehensive.source.jsonl"
ORACLE = FIXTURE_DIR / "expected-semantics.json"


def _valid_document() -> dict[str, object]:
    """Build the canonical redacted candidate from the committed source fixture."""
    with SOURCE.open(encoding="utf-8") as source_file:
        return redact_trajectory(parse_claude_jsonl(source_file)).to_json_dict()


def _write_document(tmp_path: Path, document: dict[str, object]) -> Path:
    """Write a candidate document to the test's isolated temporary directory."""
    path = tmp_path / "candidate.atif.json"
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return path


def _verify(tmp_path: Path, document: dict[str, object]) -> dict[str, object]:
    """Verify a candidate against the canonical source and oracle."""
    return verify_files(SOURCE, _write_document(tmp_path, document), ORACLE)


def test_canonical_fixture_passes_semantic_verifier(tmp_path: Path):
    """The committed canonical candidate satisfies every ASB semantic finding."""
    report = _verify(tmp_path, _valid_document())

    assert report["summary"] == {"passed": True, "findings": 15, "conflicts": 0}
    assert all(finding["state"] != "CONFLICT" for finding in report["findings"])
    Trajectory.model_validate(_valid_document())


@pytest.mark.parametrize(
    "mutation",
    [
        "swapped_results",
        "missing_call",
        "duplicate_result",
        "wrong_call_id",
        "changed_arguments",
        "reordered_steps",
        "omitted_text",
        "fabricated_timestamp",
        "false_fidelity",
        "redaction_failure",
        "unsupported_claimed_preserved",
    ],
)
def test_negative_controls_reject_mutated_documents(
    tmp_path: Path, mutation: str
):
    """Each named mutation contradicts at least one independently checked fact."""
    document = copy.deepcopy(_valid_document())
    steps = document["steps"]
    assert isinstance(steps, list)
    action = steps[1]
    assert isinstance(action, dict)
    observation = action["observation"]
    assert isinstance(observation, dict)
    results = observation["results"]
    assert isinstance(results, list)
    calls = action["tool_calls"]
    assert isinstance(calls, list)

    if mutation == "swapped_results":
        results[0]["content"], results[1]["content"] = (
            results[1]["content"],
            results[0]["content"],
        )
    elif mutation == "missing_call":
        calls.pop()
    elif mutation == "duplicate_result":
        results.append(copy.deepcopy(results[0]))
    elif mutation == "wrong_call_id":
        results[0]["source_call_id"] = "call-not-in-source"
    elif mutation == "changed_arguments":
        calls[0]["arguments"]["path"] = "wrong.txt"
    elif mutation == "reordered_steps":
        steps[2], steps[3] = steps[3], steps[2]
    elif mutation == "omitted_text":
        steps[0]["message"] = ""
    elif mutation == "fabricated_timestamp":
        steps[0]["timestamp"] = "2026-08-31T12:00:99Z"
    elif mutation == "false_fidelity":
        document["extra"]["agent_session_bridge"]["fidelity"]["observation_results_preserved"] = 0
    elif mutation == "redaction_failure":
        calls[0]["arguments"]["credential"] = "sk-test-THIS_IS_NOT_A_REAL_KEY_123456"
    elif mutation == "unsupported_claimed_preserved":
        document["extra"]["agent_session_bridge"]["fidelity"]["unsupported_source_blocks"] = 0

    report = _verify(tmp_path, document)
    assert report["summary"]["passed"] is False
    assert report["summary"]["conflicts"] >= 1


def test_valid_document_remains_valid_after_negative_controls(tmp_path: Path):
    """A fresh canonical candidate still passes after mutation tests complete."""
    report = _verify(tmp_path, _valid_document())

    assert report["summary"]["passed"] is True


def test_reproduction_command_writes_a_valid_atif_document(tmp_path: Path):
    """The public reproduction command emits a model-valid ATIF v1.7 document."""
    output = tmp_path / "reproduced.atif.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "interoperability.reproduce",
            "--source",
            str(SOURCE),
            "--output",
            str(output),
        ],
        check=True,
        timeout=120,
    )

    document = json.loads(output.read_text(encoding="utf-8"))
    assert Trajectory.model_validate(document).schema_version == "ATIF-v1.7"


def _shifted_source_case(
    tmp_path: Path, unsupported_line: str, unsupported_type: str
) -> tuple[Path, Path, Path]:
    """Insert one unsupported non-empty line and shift the oracle's indexed facts."""
    source_lines = SOURCE.read_text(encoding="utf-8").splitlines()
    source_lines.insert(1, unsupported_line)
    source = tmp_path / "shifted.source.jsonl"
    source.write_text("\n".join(source_lines) + "\n", encoding="utf-8")

    oracle = copy.deepcopy(json.loads(ORACLE.read_text(encoding="utf-8")))
    source_facts: dict[str, Any] = oracle["source_facts"]
    source_facts["source_timestamps"].insert(1, None)
    source_facts["ignored_source_fields"][0]["record"] = 3
    source_facts["unsupported_source_records"].insert(
        1, {"record": 2, "type": unsupported_type, "expected_state": "omitted"}
    )
    oracle["asb_policy"]["expected_fidelity"]["unsupported_source_records"] = 3
    oracle_path = tmp_path / "shifted.expected-semantics.json"
    oracle_path.write_text(json.dumps(oracle, indent=2) + "\n", encoding="utf-8")

    with source.open(encoding="utf-8") as source_file:
        document = redact_trajectory(parse_claude_jsonl(source_file)).to_json_dict()
    output_path = _write_document(tmp_path, document)
    return source, output_path, oracle_path


def test_source_reader_keeps_positions_for_malformed_and_non_object_lines(
    tmp_path: Path,
):
    """Malformed and non-object non-empty lines become aligned unsupported sentinels."""
    source = tmp_path / "invalid.source.jsonl"
    source.write_text('{"type":"user"}\nnot-json\n[]\n', encoding="utf-8")

    records = _read_source(source)

    assert len(records) == 3
    assert records[0] == {"type": "user"}
    assert records[1] == {"_asb_unsupported_source_record": True}
    assert records[2] == {"_asb_unsupported_source_record": True}


@pytest.mark.parametrize(
    ("unsupported_line", "unsupported_type"),
    [("not-json", "malformed"), ("[]", "array")],
)
def test_unsupported_source_lines_do_not_shift_ignored_field_oracle_indices(
    tmp_path: Path, unsupported_line: str, unsupported_type: str
):
    """The verifier remains successful when an unsupported line precedes the ignored field."""
    source, output, oracle = _shifted_source_case(
        tmp_path, unsupported_line, unsupported_type
    )

    report = verify_files(source, output, oracle)

    assert report["summary"] == {"passed": True, "findings": 15, "conflicts": 0}
    ignored = next(
        finding for finding in report["findings"] if finding["name"] == "ignored_source_field"
    )
    assert ignored["state"] == "OMITTED"


def test_peer_unsupported_record_finding_is_not_a_self_comparison(tmp_path: Path):
    """Peer reports mark ASB-only unsupported-record accounting as not applicable."""
    report = verify_files(
        SOURCE,
        _write_document(tmp_path, _valid_document()),
        ORACLE,
        implementation="peer-example",
    )

    finding = next(
        item
        for item in report["findings"]
        if item["name"] == "unsupported_source_record_is_omitted"
    )

    assert finding["state"] == "NOT_APPLICABLE"
    assert "do not report an ASB fidelity record count" in finding["detail"]
