from adapters.claude.parser import parse_claude_jsonl


def test_parse_claude_sample():
    with open("fixtures/claude_sample.jsonl", "r") as f:
        session = parse_claude_jsonl(f)
    
    assert session.session_id == "s1"
    assert session.workspace.cwd == "/dev/workspace"
    assert session.workspace.repository.branch == "main"
    assert len(session.turns) == 4
    
    # Check tool use
    assert session.turns[1].tool_invocations[0].name == "ls"
    assert session.turns[1].tool_invocations[0].tool_id == "t1"
    
    # Check tool result
    assert session.turns[2].tool_results[0].tool_id == "t1"
    assert "file1.txt" in session.turns[2].tool_results[0].output
    
    # Check loss report
    loss = session.provenance.loss_report
    assert loss.turns_preserved == 4
    assert loss.tools_preserved == 2 # 1 use, 1 result
    assert loss.unsupported_events == 0
