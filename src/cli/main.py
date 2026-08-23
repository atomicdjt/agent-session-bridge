import argparse
import sys

from adapters.antigravity.exporter import export_with_report
from adapters.claude.parser import parse_claude_jsonl
from security.redact import redact_trajectory


def import_session(args: argparse.Namespace) -> None:
    with open(args.source, encoding="utf-8") as source_file:
        if args.from_format != "claude-code":
            print(f"Unsupported format: {args.from_format}")
            sys.exit(1)
        trajectory = redact_trajectory(parse_claude_jsonl(source_file))

    output = trajectory.model_dump_json(indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as output_file:
            output_file.write(output)
        print(f"ATIF trajectory written to {args.output}")
    else:
        print(output)

    if args.report:
        bridge = (trajectory.extra or {}).get("agent_session_bridge")
        if not isinstance(bridge, dict):
            raise RuntimeError("ATIF trajectory is missing ASB conversion metadata.")
        fidelity = bridge.get("fidelity")
        if not isinstance(fidelity, dict):
            raise RuntimeError("ATIF trajectory is missing an ASB fidelity report.")
        print("\n--- ASB Fidelity Report ---")
        print(f"Source records preserved: {fidelity['source_records_preserved']}")
        print(f"Tool calls preserved:     {fidelity['tool_calls_preserved']}")
        print(f"Observations preserved:   {fidelity['observation_results_preserved']}")
        print(f"Unsupported records:      {fidelity['unsupported_source_records']}")
        print(f"Unsupported blocks:       {fidelity['unsupported_source_blocks']}")
        print("---------------------------")


def convert_session(args: argparse.Namespace) -> None:
    with open(args.file, encoding="utf-8") as source_file:
        if args.from_format != "claude-code":
            print(f"Unsupported source format: {args.from_format}")
            sys.exit(1)
        trajectory = redact_trajectory(parse_claude_jsonl(source_file))

    if args.to_format != "antigravity":
        print(f"Unsupported target format: {args.to_format}")
        sys.exit(1)
    exported = export_with_report(trajectory)
    if exported.omitted_system_messages:
        print(
            "ASB target-mapping warning: omitted "
            f"{exported.omitted_system_messages} system message(s) because the observed "
            "Antigravity derived-log shape has no evidenced system-message mapping.",
            file=sys.stderr,
        )
    print(exported.payload)


def handoff_session(args: argparse.Namespace) -> None:
    print("STATUS: UnsupportedNativeImport")
    print(
        "Reason: Antigravity CLI does not currently expose a supported "
        "'import-session' or public API for writing session state."
    )
    print(
        "Rule check: Silently mutating the internal `.system_generated` databases "
        "is strictly forbidden by the security guidelines."
    )
    print(
        "Action: Outputting an ATIF-derived JSONL payload that could be supplied "
        "to an `agy import-session` command once one exists."
    )
    print("=" * 80)
    convert_session(args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent Session Bridge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser(
        "import", help="Normalize a supported source transcript into ATIF v1.7."
    )
    import_parser.add_argument("--source", required=True)
    import_parser.add_argument(
        "--from", dest="from_format", required=True, choices=["claude-code"]
    )
    import_parser.add_argument("--output")
    import_parser.add_argument("--report", action="store_true")
    import_parser.set_defaults(func=import_session)

    convert_parser = subparsers.add_parser("convert")
    convert_parser.add_argument(
        "--from", dest="from_format", required=True, choices=["claude-code"]
    )
    convert_parser.add_argument(
        "--to", dest="to_format", required=True, choices=["antigravity"]
    )
    convert_parser.add_argument("file")
    convert_parser.set_defaults(func=convert_session)

    handoff_parser = subparsers.add_parser("handoff")
    handoff_parser.add_argument(
        "--from", dest="from_format", required=True, choices=["claude-code"]
    )
    handoff_parser.add_argument(
        "--to", dest="to_format", required=True, choices=["antigravity"]
    )
    handoff_parser.add_argument("file")
    handoff_parser.set_defaults(func=handoff_session)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
