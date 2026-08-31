from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from atif import Trajectory

from adapters.claude.parser import parse_claude_jsonl
from interoperability.verifier import verify_files
from security.redact import redact_trajectory

FIXTURE_DIR = Path("fixtures/interoperability")
SOURCE = FIXTURE_DIR / "claude-comprehensive.source.jsonl"
ORACLE = FIXTURE_DIR / "expected-semantics.json"


def _valid_document() -> dict[str, object]:
    with SOURCE.open(encoding="utf-8") as source_file:
        return redact_trajectory(parse_claude_jsonl(source_file)).to_json_dict()


def _write_document(tmp_path: Path, document: dict[str, object]) -> Path:
    path = tmp_path / "candidate.atif.json"
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return path


def _verify(tmp_path: Path, document: dict[str, object]) -> dict[str, object]:
    return verify_files(SOURCE, _write_document(tmp_path, document), ORACLE)


def test_canonical_fixture_passes_semantic_verifier(tmp_path: Path):
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
    report = _verify(tmp_path, _valid_document())

    assert report["summary"]["passed"] is True


def test_reproduction_command_writes_a_valid_atif_document(tmp_path: Path):
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
    )

    document = json.loads(output.read_text(encoding="utf-8"))
    assert Trajectory.model_validate(document).schema_version == "ATIF-v1.7"
