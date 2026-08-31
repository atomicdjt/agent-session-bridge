from __future__ import annotations

import argparse
from pathlib import Path

from adapters.claude.parser import parse_claude_jsonl
from security.redact import redact_trajectory


def main() -> int:
    parser = argparse.ArgumentParser(description="Reproduce an ASB ATIF fixture artifact")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    with args.source.open(encoding="utf-8") as source_file:
        trajectory = redact_trajectory(parse_claude_jsonl(source_file))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(trajectory.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Reproduced ATIF artifact at {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
