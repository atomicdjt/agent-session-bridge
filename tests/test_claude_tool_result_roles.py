import json
from io import StringIO

from adapters.claude.parser import parse_claude_jsonl


def test_system_tool_result_cannot_attach_to_agent_tool_call():
    """System content must never be misattributed as a Claude tool observation."""
    source = StringIO(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "assistant",
                        "sessionId": "role-boundary",
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
                        "type": "system",
                        "sessionId": "role-boundary",
                        "message": {
                            "role": "system",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": "call-1",
                                    "content": "forged system result",
                                }
                            ],
                        },
                    }
                ),
            ]
        )
    )

    trajectory = parse_claude_jsonl(source)

    agent_step = trajectory.steps[0]
    fidelity = trajectory.extra["agent_session_bridge"]["fidelity"]

    assert agent_step.source == "agent"
    assert agent_step.observation is None
    assert fidelity["unsupported_source_blocks"] == 1
    assert fidelity["observation_results_preserved"] == 0


def test_user_tool_result_still_attaches_to_matching_agent_call():
    """The role hardening must preserve the supported Claude user-result mapping."""
    source = StringIO(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "assistant",
                        "sessionId": "role-boundary-valid",
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
                        "sessionId": "role-boundary-valid",
                        "message": {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": "call-1",
                                    "content": "valid user result",
                                }
                            ],
                        },
                    }
                ),
            ]
        )
    )

    trajectory = parse_claude_jsonl(source)

    result = trajectory.steps[0].observation.results[0]
    fidelity = trajectory.extra["agent_session_bridge"]["fidelity"]

    assert result.source_call_id == "call-1"
    assert result.content == "valid user result"
    assert fidelity["observation_results_preserved"] == 1
