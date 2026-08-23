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
