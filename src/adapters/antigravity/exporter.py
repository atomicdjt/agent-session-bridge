import json
from canonical.models import ASEFSession, MessageRole

def export_to_antigravity(session: ASEFSession) -> str:
    transcript_lines = []
    
    for idx, turn in enumerate(session.turns, 1):
        if turn.role == MessageRole.USER:
            record = {
                "step_index": len(transcript_lines) + 1,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "status": "DONE",
                "created_at": turn.timestamp,
                "content": turn.content
            }
            transcript_lines.append(json.dumps(record))
        elif turn.role == MessageRole.ASSISTANT:
            tool_calls = []
            for t_inv in turn.tool_invocations:
                tool_calls.append({
                    "name": t_inv.name,
                    "args": {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in t_inv.arguments.items()}
                })
                
            record = {
                "step_index": len(transcript_lines) + 1,
                "source": "MODEL",
                "type": "PLANNER_RESPONSE",
                "status": "DONE",
                "created_at": turn.timestamp,
                "content": turn.content,
                "tool_calls": tool_calls
            }
            transcript_lines.append(json.dumps(record))
            
        for t_res in turn.tool_results:
            res_record = {
                "step_index": len(transcript_lines) + 1,
                "source": "SYSTEM",
                "type": "TOOL_RESPONSE",
                "status": t_res.status.upper(),
                "created_at": turn.timestamp,
                "content": t_res.output or ""
            }
            transcript_lines.append(json.dumps(res_record))
                
    return "\n".join(transcript_lines) + "\n"
