import json
from typing import TextIO

from canonical.models import (
    ASEFSession,
    LossReport,
    MessageRole,
    Provenance,
    ProviderInfo,
    RepoMetadata,
    ToolInvocation,
    ToolResult,
    Turn,
    Workspace,
)


def parse_claude_jsonl(file_stream: TextIO) -> ASEFSession:
    turns: list[Turn] = []
    session_id = "unknown"
    version = "unknown"
    cwd = ""
    git_branch = None
    
    loss = LossReport()
    
    for line in file_stream:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            loss.unsupported_events += 1
            continue
            
        record_type = record.get("type")
        if not record_type:
            loss.unsupported_events += 1
            continue
            
        # Extract metadata if present
        if "sessionId" in record and session_id == "unknown":
            session_id = record["sessionId"]
        if "version" in record and version == "unknown":
            version = record["version"]
        if "cwd" in record and not cwd:
            cwd = record["cwd"]
        if "gitBranch" in record and not git_branch:
            git_branch = record["gitBranch"]
            
        if record_type in ["user", "assistant", "system"]:
            uuid = record.get("uuid", "")
            timestamp = record.get("timestamp", "")
            message = record.get("message", {})
            role_str = message.get("role", record_type)
            content_blocks = message.get("content", [])
            
            try:
                role = MessageRole(role_str)
            except ValueError:
                role = MessageRole.SYSTEM
            
            text_content = ""
            tool_invocations = []
            tool_results = []
            
            if isinstance(content_blocks, str):
                text_content = content_blocks
            elif isinstance(content_blocks, list):
                for block in content_blocks:
                    if not isinstance(block, dict):
                        continue
                    b_type = block.get("type", "")
                    if b_type == "text":
                        text_content += block.get("text", "") + "\n"
                    elif b_type == "tool_use":
                        tool_invocations.append(ToolInvocation(
                            tool_id=block.get("id", ""),
                            name=block.get("name", ""),
                            arguments=block.get("input", {})
                        ))
                        loss.tools_preserved += 1
                    elif b_type == "tool_result":
                        # We extract output
                        out_val = block.get("content", "")
                        if isinstance(out_val, list):
                            out_str = "".join(b.get("text", "") for b in out_val if isinstance(b, dict) and b.get("type") == "text")
                        else:
                            out_str = str(out_val)
                        tool_results.append(ToolResult(
                            tool_id=block.get("tool_use_id", ""),
                            status="success" if not block.get("is_error") else "error",
                            output=out_str
                        ))
                        loss.tools_preserved += 1
                    else:
                        loss.unsupported_events += 1
            
            turn = Turn(
                turn_id=uuid,
                role=role,
                timestamp=timestamp,
                content=text_content.strip(),
                tool_invocations=tool_invocations,
                tool_results=tool_results
            )
            turns.append(turn)
            loss.turns_preserved += 1
        else:
            loss.unsupported_events += 1
            
    repo_meta = RepoMetadata(branch=git_branch) if git_branch else None
    
    return ASEFSession(
        session_id=session_id,
        source=ProviderInfo(provider="anthropic", agent="claude-code", version=version),
        workspace=Workspace(cwd=cwd, repository=repo_meta),
        turns=turns,
        provenance=Provenance(
            original_format="claude-code-jsonl",
            conversion_timestamp="now",
            converted_by="agent-session-bridge",
            loss_report=loss
        )
    )
