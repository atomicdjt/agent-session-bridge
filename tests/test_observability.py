import json
from datetime import datetime

import pytest
from atif import Trajectory
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from observability.spans import project_trajectory

_global_exporter = InMemorySpanExporter()
_global_provider = TracerProvider()
_global_provider.add_span_processor(SimpleSpanProcessor(_global_exporter))
trace.set_tracer_provider(_global_provider)


@pytest.fixture
def memory_exporter():
    _global_exporter.clear()
    return _global_exporter


def test_project_trajectory_metadata_only(memory_exporter):
    with open("fixtures/claude_sample.atif.json", "r") as f:
        data = json.load(f)
    trajectory = Trajectory.model_validate(data)

    project_trajectory(trajectory, privacy_mode="metadata-only")

    spans = memory_exporter.get_finished_spans()

    # We expect 1 root span, 3 step spans, 1 tool span
    assert len(spans) == 5

    # Check root span
    root = spans[-1]
    assert root.name == "historical_trajectory"
    assert root.attributes["session.id"] == "s1"
    assert root.attributes["openinference.span.kind"] == "CHAIN"

    # Check tool span
    tool_spans = [
        s for s in spans if s.attributes.get("openinference.span.kind") == "TOOL"
    ]
    assert len(tool_spans) == 1
    tool = tool_spans[0]
    assert tool.name == "ls"
    assert "input.value" not in tool.attributes
    assert "output.value" not in tool.attributes
    assert tool.attributes["agent_session_bridge.tool_id"] == "t1"


def test_project_trajectory_full_content(memory_exporter):
    with open("fixtures/claude_sample.atif.json", "r") as f:
        data = json.load(f)
    trajectory = Trajectory.model_validate(data)

    project_trajectory(trajectory, privacy_mode="full-content")

    spans = memory_exporter.get_finished_spans()

    tool_spans = [
        s for s in spans if s.attributes.get("openinference.span.kind") == "TOOL"
    ]
    tool = tool_spans[0]
    assert "input.value" in tool.attributes
    assert "output.value" in tool.attributes
    assert "file1.txt" in tool.attributes["output.value"]


def test_metadata_only_leaks_no_sensitive_content(memory_exporter):
    with open("fixtures/claude_sample.atif.json", "r") as f:
        trajectory = Trajectory.model_validate(json.load(f))
    sensitive = "SECRET_TOKEN_DO_NOT_EXPORT PRIVATE_SOURCE_TEXT_DO_NOT_EXPORT C:\\Users\\Example\\SecretProject password=example-secret api_key=example-key"
    trajectory.steps[1].message = sensitive
    trajectory.steps[1].tool_calls[0].arguments = {"value": sensitive}
    trajectory.steps[1].observation.results[0].content = sensitive

    project_trajectory(trajectory, privacy_mode="metadata-only")

    rendered = "\n".join(
        str(value)
        for span in memory_exporter.get_finished_spans()
        for value in (span.name, *span.attributes.values())
    )
    assert "SECRET_TOKEN_DO_NOT_EXPORT" not in rendered
    assert "PRIVATE_SOURCE_TEXT_DO_NOT_EXPORT" not in rendered
    assert "example-secret" not in rendered


def test_redacted_content_redacts_and_full_content_preserves(memory_exporter):
    with open("fixtures/claude_sample.atif.json", "r") as f:
        trajectory = Trajectory.model_validate(json.load(f))
    sensitive = 'secret_key="SECRET_TOKEN_DO_NOT_EXPORT" password="example-secret"'
    trajectory.steps[1].message = sensitive
    trajectory.steps[1].tool_calls[0].arguments = {"value": sensitive}
    trajectory.steps[1].observation.results[0].content = sensitive

    project_trajectory(trajectory, privacy_mode="redacted-content")
    redacted = "\n".join(
        str(value)
        for span in memory_exporter.get_finished_spans()
        for value in span.attributes.values()
    )
    assert "SECRET_TOKEN_DO_NOT_EXPORT" not in redacted
    assert "example-secret" not in redacted

    memory_exporter.clear()
    project_trajectory(trajectory, privacy_mode="full-content")
    full = "\n".join(
        str(value)
        for span in memory_exporter.get_finished_spans()
        for value in span.attributes.values()
    )
    assert "SECRET_TOKEN_DO_NOT_EXPORT" in full
    assert "example-secret" in full


def test_session_id_is_emitted_only_when_source_provides_one(memory_exporter):
    with open("fixtures/claude_sample.atif.json", "r") as f:
        trajectory = Trajectory.model_validate(json.load(f))
    project_trajectory(trajectory)
    assert all(
        span.attributes.get("session.id") == "s1"
        for span in memory_exporter.get_finished_spans()
    )

    memory_exporter.clear()
    trajectory.session_id = "unknown"
    project_trajectory(trajectory)
    assert all(
        "session.id" not in span.attributes
        for span in memory_exporter.get_finished_spans()
    )


def test_timestamps_are_observed_points_or_correlated_boundaries(memory_exporter):
    with open("fixtures/claude_sample.atif.json", "r") as f:
        trajectory = Trajectory.model_validate(json.load(f))
    project_trajectory(trajectory)
    spans = memory_exporter.get_finished_spans()
    tool = next(
        span
        for span in spans
        if span.attributes.get("openinference.span.kind") == "TOOL"
    )
    assistant_time = int(
        datetime.fromisoformat("2026-08-21T10:00:02+00:00").timestamp() * 1e9
    )
    # The result has no separate timestamp, tool end is the start time.
    assert tool.start_time == assistant_time
    assert tool.end_time == assistant_time
    assert (
        tool.attributes["agent_session_bridge.timestamp.provenance"] == "SOURCE_OBSERVED"
    )
    assert all(span.end_time >= span.start_time for span in spans)


def test_missing_timestamp_is_rejected_instead_of_fabricated(memory_exporter):
    with open("fixtures/claude_sample.atif.json", "r") as f:
        trajectory = Trajectory.model_validate(json.load(f))
    trajectory.steps[0].timestamp = ""
    with pytest.raises(ValueError, match="source-observed ISO-8601"):
        project_trajectory(trajectory)


def test_missing_timestamp_in_later_step_is_rejected_before_any_spans_created(memory_exporter):
    with open("fixtures/claude_sample.atif.json", "r") as f:
        trajectory = Trajectory.model_validate(json.load(f))
    # valid timestamp on step 0, invalid on step 1
    assert trajectory.steps[0].timestamp
    trajectory.steps[1].timestamp = ""

    with pytest.raises(ValueError, match="source-observed ISO-8601"):
        project_trajectory(trajectory)

    # Should fail BEFORE exporting any spans
    assert len(memory_exporter.get_finished_spans()) == 0


import argparse
from unittest.mock import patch

from cli.main import observe_session


def test_cli_observe_preserves_content_in_full_content_mode(memory_exporter, tmp_path):
    source_file = tmp_path / "sensitive.jsonl"
    sensitive_value = "SECRET_TOKEN_DO_NOT_EXPORT"
    source_file.write_text(json.dumps({
        "type": "user",
        "sessionId": "s4",
        "timestamp": "2026-08-21T10:00:00Z",
        "version": "1.0",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": f'api_key="{sensitive_value}"'}],
        },
    }), encoding="utf-8")

    args = argparse.Namespace(
        from_format="claude-code",
        backend="phoenix",
        endpoint="",
        privacy="full-content",
        console=False,
        file=str(source_file)
    )

    with patch("observability.exporter.setup_exporter", return_value=_global_provider):
        observe_session(args)

    spans = memory_exporter.get_finished_spans()
    full = "\n".join(str(value) for span in spans for value in span.attributes.values())
    assert sensitive_value in full


def test_cli_observe_redacts_content_in_redacted_content_mode(memory_exporter, tmp_path):
    source_file = tmp_path / "sensitive.jsonl"
    sensitive_value = "SECRET_TOKEN_DO_NOT_EXPORT"
    source_file.write_text(json.dumps({
        "type": "user",
        "sessionId": "s4",
        "timestamp": "2026-08-21T10:00:00Z",
        "version": "1.0",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": f'api_key="{sensitive_value}"'}],
        },
    }), encoding="utf-8")

    args = argparse.Namespace(
        from_format="claude-code",
        backend="phoenix",
        endpoint="",
        privacy="redacted-content",
        console=False,
        file=str(source_file)
    )

    with patch("observability.exporter.setup_exporter", return_value=_global_provider):
        observe_session(args)

    spans = memory_exporter.get_finished_spans()
    redacted = "\n".join(str(value) for span in spans for value in span.attributes.values())
    assert sensitive_value not in redacted
    assert "[REDACTED]" in redacted


def test_cli_observe_metadata_only_mode(memory_exporter, tmp_path):
    source_file = tmp_path / "sensitive.jsonl"
    sensitive_value = "SECRET_TOKEN_DO_NOT_EXPORT"
    source_file.write_text(json.dumps({
        "type": "user",
        "sessionId": "s4",
        "timestamp": "2026-08-21T10:00:00Z",
        "version": "1.0",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": f'api_key="{sensitive_value}"'}],
        },
    }), encoding="utf-8")

    args = argparse.Namespace(
        from_format="claude-code",
        backend="phoenix",
        endpoint="",
        privacy="metadata-only",
        console=False,
        file=str(source_file)
    )

    with patch("observability.exporter.setup_exporter", return_value=_global_provider):
        observe_session(args)

    spans = memory_exporter.get_finished_spans()
    metadata = "\n".join(str(value) for span in spans for value in span.attributes.values())
    assert sensitive_value not in metadata
    assert "[REDACTED]" not in metadata


def test_timezone_naive_timestamp_rejected(memory_exporter):
    with open("fixtures/claude_sample.atif.json", "r") as f:
        trajectory = Trajectory.model_validate(json.load(f))
    trajectory.steps[0].timestamp = "2026-08-21T10:00:00"
    with pytest.raises(ValueError, match="source-observed ISO-8601 timestamp for every step"):
        project_trajectory(trajectory)
    assert len(memory_exporter.get_finished_spans()) == 0


def test_timezone_aware_timestamps_accepted(memory_exporter):
    with open("fixtures/claude_sample.atif.json", "r") as f:
        trajectory = Trajectory.model_validate(json.load(f))
    valid_times = [
        "2026-08-21T10:00:00Z",
        "2026-08-21T10:00:00+00:00",
        "2026-08-21T10:00:00-05:00"
    ]
    for step, tz_time in zip(trajectory.steps, valid_times):
        step.timestamp = tz_time
    for step in trajectory.steps[len(valid_times):]:
        step.timestamp = valid_times[0]

    project_trajectory(trajectory)
    assert len(memory_exporter.get_finished_spans()) > 0


def test_cli_observe_empty_atif_trajectory_fails_before_exporter_setup(memory_exporter, tmp_path, capsys):
    source_file = tmp_path / "empty.json"
    source_file.write_text(json.dumps({
        "schema_version": "ATIF-v1.7",
        "session_id": "empty1",
        "agent": {"name": "test", "version": "1.0"},
        "steps": []
    }), encoding="utf-8")

    args = argparse.Namespace(
        from_format="atif",
        backend="phoenix",
        endpoint="",
        privacy="metadata-only",
        console=False,
        file=str(source_file)
    )

    with patch("observability.exporter.setup_exporter") as mock_setup:
        with pytest.raises(SystemExit) as exc:
            observe_session(args)
        assert exc.value.code == 1

    mock_setup.assert_not_called()
    captured = capsys.readouterr()
    assert "Error: trajectory contains no valid steps to export." in captured.out


def test_cli_observe_empty_claude_trajectory_fails_before_exporter_setup(memory_exporter, tmp_path, capsys):
    source_file = tmp_path / "empty_claude.jsonl"
    source_file.write_text("", encoding="utf-8")

    args = argparse.Namespace(
        from_format="claude-code",
        backend="phoenix",
        endpoint="",
        privacy="metadata-only",
        console=False,
        file=str(source_file)
    )

    with patch("observability.exporter.setup_exporter") as mock_setup:
        with pytest.raises(SystemExit) as exc:
            observe_session(args)
        assert exc.value.code == 1

    mock_setup.assert_not_called()
    captured = capsys.readouterr()
    assert "Error: trajectory contains no valid steps to export." in captured.out


def test_parse_source_time_exact_precision():
    from observability.spans import parse_source_time

    # 1. 1970-01-01T00:00:00.000001+00:00
    assert parse_source_time("1970-01-01T00:00:00.000001+00:00") == 1000

    # 2. Modern UTC timestamp with microseconds
    assert parse_source_time("2026-08-21T10:15:30.123456Z") == 1787307330123456000
    assert parse_source_time("2026-08-21T10:15:30.123456+00:00") == 1787307330123456000

    # 3. Modern timestamp with a positive UTC offset
    assert parse_source_time("2026-08-21T10:15:30.123456+02:00") == 1787300130123456000

    # 4. Modern timestamp with a negative UTC offset
    assert parse_source_time("2026-08-21T10:15:30.123456-05:00") == 1787325330123456000

    # 5. Boundary testing near datetime.min and datetime.max
    assert parse_source_time("0001-01-01T00:00:00+01:00") == -62135600400000000000
    assert parse_source_time("9999-12-31T23:59:59-01:00") == 253402304399000000000
