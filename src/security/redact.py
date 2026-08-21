import re

from canonical.models import ASEFSession

SECRET_PATTERNS = [
    # Very basic naive patterns for demo purposes
    (re.compile(r'(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|password)\s*[:=]\s*["\'][a-zA-Z0-9_\-\.]{10,}["\']'), r'\1 = "[REDACTED]"'),
    (re.compile(r'xox[baprs]-[0-9a-zA-Z]{10,}'), 'xox?-***REDACTED***')
]

def redact_session(session: ASEFSession) -> ASEFSession:
    # Iterate through content and tool outputs and redact sensitive data
    for turn in session.turns:
        for pattern, replacement in SECRET_PATTERNS:
            if turn.content:
                turn.content = pattern.sub(replacement, turn.content)
            for res in turn.tool_results:
                if res.output:
                    res.output = pattern.sub(replacement, res.output)
            for inv in turn.tool_invocations:
                for k, v in inv.arguments.items():
                    if isinstance(v, str):
                        inv.arguments[k] = pattern.sub(replacement, v)
    return session
