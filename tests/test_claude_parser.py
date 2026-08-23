from atif import Trajectory

from adapters.claude.parser import parse_claude_jsonl


def test_parse_claude_sample():
    with open("fixtures/claude_sample.jsonl", "r") as f:
        trajectory = parse_claude_jsonl(f)
    
    assert isinstance(trajectory, Trajectory)
    assert trajectory.session_id == "s1"
    assert trajectory.extra["agent_session_bridge"]["workspace"]["cwd"] == "/dev/workspace"
    assert trajectory.extra["agent_session_bridge"]["workspace"]["repository"]["branch"] == "main"
    assert len(trajectory.steps) == 3
    
    # Check tool use
    assert trajectory.steps[1].tool_calls[0].function_name == "ls"
    assert trajectory.steps[1].tool_calls[0].tool_call_id == "t1"
    
    # Check tool result
    assert trajectory.steps[1].observation.results[0].source_call_id == "t1"
    assert "file1.txt" in trajectory.steps[1].observation.results[0].content
    
    # Check loss report
    fidelity = trajectory.extra["agent_session_bridge"]["fidelity"]
    assert fidelity["source_records_preserved"] == 4
    assert fidelity["tool_calls_preserved"] == 1
    assert fidelity["observation_results_preserved"] == 1
    assert fidelity["unsupported_source_records"] == 0
