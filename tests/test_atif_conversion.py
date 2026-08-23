import json
import subprocess
import sys
from io import StringIO
from pathlib import Path

from atif import Agent, Step, Trajectory

from adapters.antigravity.exporter import export_to_antigravity, export_with_report
from adapters.claude.parser import parse_claude_jsonl
from security.redact import redact_trajectory

FIXTURE = Path("fixtures/claude_sample.jsonl")


def test_parser_emits_atif_and_correlates_tool_results_to_calls():
    """Fails if the parser returns a proprietary session or detaches a tool result."""
    with FIXTURE.open(encoding="utf-8") as file_stream:
        trajectory = parse_claude_jsonl(file_stream)

    assert isinstance(trajectory, Trajectory)
    assert trajectory.schema_version == "ATIF-v1.7"
    assert [step.source for step in trajectory.steps] == ["user", "agent", "agent"]

    action_step = trajectory.steps[1]
    assert action_step.tool_calls[0].tool_call_id == "t1"
    assert action_step.tool_calls[0].function_name == "ls"
    assert action_step.observation.results[0].source_call_id == "t1"
    assert action_step.observation.results[0].content == "file1.txt\nfile2.py"

    bridge = trajectory.extra["agent_session_bridge"]
    assert bridge["fidelity"]["source_records_preserved"] == 4
    assert bridge["fidelity"]["tool_calls_preserved"] == 1
    assert bridge["fidelity"]["observation_results_preserved"] == 1


def test_parser_preserves_user_text_next_to_tool_results_as_a_user_step():
    """Fails if folding tool-result blocks loses adjacent user-authored text."""
    source = StringIO(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "assistant",
                        "sessionId": "s2",
                        "version": "1.0",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "tool_use",
                                    "id": "call-1",
                                    "name": "read_file",
                                    "input": {"path": "README.md"},
                                }
                            ],
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": "s2",
                        "message": {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": "call-1",
                                    "content": "# Agent Session Bridge",
                                },
                                {"type": "text", "text": "Please continue."},
                            ],
                        },
                    }
                ),
            ]
        )
    )

    trajectory = parse_claude_jsonl(source)

    assert [step.source for step in trajectory.steps] == ["agent", "user"]
    assert trajectory.steps[0].observation.results[0].source_call_id == "call-1"
    assert trajectory.steps[1].message == "Please continue."


def test_parser_reports_unsupported_claude_blocks_in_asb_extension():
    """Fails if unsupported source content disappears without a fidelity record."""
    source = StringIO(
        json.dumps(
            {
                "type": "user",
                "sessionId": "s3",
                "version": "1.0",
                "message": {
                    "role": "user",
                    "content": [{"type": "image", "source": {"type": "base64"}}],
                },
            }
        )
    )

    trajectory = parse_claude_jsonl(source)

    assert trajectory.steps[0].message == ""
    assert trajectory.extra["agent_session_bridge"]["fidelity"]["unsupported_source_blocks"] == 1


def test_parser_reports_tool_calls_outside_agent_steps_as_unsupported():
    """Fails if a structurally invalid source tool call is silently discarded."""
    source = StringIO(
        json.dumps(
            {
                "type": "user",
                "sessionId": "s-tool-role",
                "version": "1.0",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call-invalid",
                            "name": "read_file",
                            "input": {"path": "README.md"},
                        }
                    ],
                },
            }
        )
    )

    trajectory = parse_claude_jsonl(source)

    assert trajectory.steps[0].source == "user"
    assert trajectory.steps[0].message == ""
    fidelity = trajectory.extra["agent_session_bridge"]["fidelity"]
    assert fidelity["tool_calls_preserved"] == 0
    assert fidelity["unsupported_source_blocks"] == 1


def test_atif_serialization_round_trip_remains_valid():
    """Fails if ASB emits data that the official ATIF validator cannot read back."""
    with FIXTURE.open(encoding="utf-8") as file_stream:
        trajectory = parse_claude_jsonl(file_stream)

    restored = Trajectory.model_validate_json(trajectory.model_dump_json())

    assert restored.to_json_dict() == trajectory.to_json_dict()


def test_redaction_preserves_a_valid_atif_trajectory():
    """Fails if redaction damages standard trajectory fields while filtering a secret."""
    source = StringIO(
        json.dumps(
            {
                "type": "user",
                "sessionId": "s4",
                "version": "1.0",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": 'api_key="abcdef0123456789"'}],
                },
            }
        )
    )

    trajectory = redact_trajectory(parse_claude_jsonl(source))

    assert trajectory.steps[0].message == 'api_key = "[REDACTED]"'
    assert Trajectory.model_validate(trajectory.to_json_dict()) == trajectory


def test_antigravity_export_preserves_atif_step_order_and_tool_response():
    """Fails if the target mapping changes the ordered portable history silently."""
    with FIXTURE.open(encoding="utf-8") as file_stream:
        trajectory = parse_claude_jsonl(file_stream)

    records = [json.loads(line) for line in export_to_antigravity(trajectory).splitlines()]

    assert [record["type"] for record in records] == [
        "USER_INPUT",
        "PLANNER_RESPONSE",
        "TOOL_RESPONSE",
        "PLANNER_RESPONSE",
    ]
    assert [record["step_index"] for record in records] == [1, 2, 3, 4]
    assert records[1]["tool_calls"] == [{"name": "ls", "args": {"dir": "."}}]
    assert records[2]["content"] == "file1.txt\nfile2.py"


def test_antigravity_export_reports_system_messages_it_cannot_map():
    """Fails if the target mapper silently drops a portable system message."""
    trajectory = Trajectory(
        schema_version="ATIF-v1.7",
        agent=Agent(name="fixture-agent", version="1.0"),
        steps=[
            Step(step_id=1, source="system", message="Do not disclose secrets."),
            Step(step_id=2, source="user", message="List files."),
        ],
    )

    exported = export_with_report(trajectory)

    assert exported.omitted_system_messages == 1
    assert [json.loads(line)["type"] for line in exported.payload.splitlines()] == [
        "USER_INPUT"
    ]


def test_cli_import_writes_an_atif_document(tmp_path: Path):
    """Fails if the public import command emits a legacy non-ATIF schema."""
    output = tmp_path / "trajectory.atif.json"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "cli.main",
            "import",
            "--from",
            "claude-code",
            "--source",
            str(FIXTURE),
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    written = Trajectory.model_validate_json(output.read_text(encoding="utf-8"))
    assert written.schema_version == "ATIF-v1.7"
    assert "ATIF trajectory written to" in completed.stdout
