import json
from datetime import datetime
from pathlib import Path

from atif import Trajectory

from adapters.antigravity.exporter import export_with_report

FIXTURE_DIR = Path("fixtures/conformance")


def _load_json(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _bridge(trajectory: Trajectory) -> dict[str, object]:
    bridge = trajectory.extra["agent_session_bridge"]
    assert isinstance(bridge, dict)
    return bridge


def test_manifest_documents_are_valid_atif_and_cover_declared_files():
    manifest = _load_json("manifest.json")
    cases = manifest["cases"]
    assert isinstance(cases, list)

    for case in cases:
        assert isinstance(case, dict)
        document = case["document"]
        assert isinstance(document, str)
        trajectory = Trajectory.model_validate(_load_json(document))
        bridge = _bridge(trajectory)
        fixture = bridge["fixture"]
        assert isinstance(fixture, dict)
        assert fixture["case"] == case["id"]
        assert fixture["states"] == case["states"]

        timestamps = [
            datetime.fromisoformat(step.timestamp)
            for step in trajectory.steps
            if step.timestamp
        ]
        assert timestamps == sorted(timestamps)


def test_tool_correlated_fixture_preserves_call_result_identity():
    trajectory = Trajectory.model_validate(
        _load_json("tool-correlated-observations.atif.json")
    )
    step = trajectory.steps[1]

    assert step.tool_calls is not None
    assert [call.tool_call_id for call in step.tool_calls] == ["fixture-call-1"]
    assert step.observation is not None
    assert [result.source_call_id for result in step.observation.results] == [
        "fixture-call-1"
    ]
    assert _bridge(trajectory)["fidelity"]["observation_results_preserved"] == 1


def test_multiple_tool_fixture_keeps_each_result_correlated():
    trajectory = Trajectory.model_validate(_load_json("multiple-tool-calls.atif.json"))
    step = trajectory.steps[0]

    assert step.tool_calls is not None
    assert [call.tool_call_id for call in step.tool_calls] == [
        "fixture-call-a",
        "fixture-call-b",
    ]
    assert step.observation is not None
    assert [result.source_call_id for result in step.observation.results] == [
        "fixture-call-a",
        "fixture-call-b",
    ]


def test_degraded_and_unsupported_states_are_explicit():
    trajectory = Trajectory.model_validate(_load_json("degraded-fidelity.atif.json"))
    bridge = _bridge(trajectory)
    fixture = bridge["fixture"]
    fidelity = bridge["fidelity"]

    assert fixture["states"] == ["degraded", "unsupported"]
    assert fidelity["unsupported_source_records"] == 1
    assert fidelity["unsupported_source_blocks"] == 2
    assert len(fidelity["transformations"]) == 2


def test_target_omission_is_reported_and_matches_reference_export():
    trajectory = Trajectory.model_validate(_load_json("target-omitted.atif.json"))
    report = export_with_report(trajectory)
    bridge = _bridge(trajectory)
    omissions = bridge["target_omissions"]

    assert report.omitted_system_messages == 1
    assert isinstance(omissions, list)
    assert omissions[0]["count"] == report.omitted_system_messages
    assert omissions[0]["target"] == "antigravity-derived-log"


def test_chronological_pair_makes_source_and_expected_order_visible():
    source_lines = (FIXTURE_DIR / "chronological-normalization.source.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    source_timestamps = [
        json.loads(line)["timestamp"] for line in source_lines if line.strip()
    ]
    expected = Trajectory.model_validate(
        _load_json("chronological-normalization.expected.atif.json")
    )
    expected_timestamps = [step.timestamp for step in expected.steps]

    assert source_timestamps != sorted(source_timestamps)
    assert expected_timestamps == sorted(expected_timestamps)
    assert _bridge(expected)["fixture"]["states"] == ["normalized"]

