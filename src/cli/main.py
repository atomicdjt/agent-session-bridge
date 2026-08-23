import argparse
import json
import sys

from adapters.antigravity.exporter import export_with_report
from adapters.claude.parser import parse_claude_jsonl
from security.redact import redact_trajectory


def import_session(args: argparse.Namespace) -> None:
    with open(args.source, encoding="utf-8") as source_file:
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
        print("\n--- ASB Fidelity Report ---", file=sys.stderr)
        print(
            f"Source records preserved: {fidelity['source_records_preserved']}",
            file=sys.stderr,
        )
        print(f"Tool calls preserved:     {fidelity['tool_calls_preserved']}", file=sys.stderr)
        print(
            f"Observations preserved:   {fidelity['observation_results_preserved']}",
            file=sys.stderr,
        )
        print(f"Unsupported records:      {fidelity['unsupported_source_records']}", file=sys.stderr)
        print(f"Unsupported blocks:       {fidelity['unsupported_source_blocks']}", file=sys.stderr)
        print("---------------------------", file=sys.stderr)


def convert_session(args: argparse.Namespace) -> None:
    with open(args.file, encoding="utf-8") as source_file:
        trajectory = redact_trajectory(parse_claude_jsonl(source_file))

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


def observe_session(args: argparse.Namespace) -> None:
    try:
        from observability.exporter import setup_exporter
        from observability.spans import project_trajectory
    except ImportError:
        print('Observability dependencies missing. Install with: pip install -e ".[observability]"')
        sys.exit(1)

    with open(args.file, "r", encoding="utf-8") as f:
        if args.from_format == "claude-code":
            trajectory = redact_trajectory(parse_claude_jsonl(f))
        elif args.from_format == "atif":
            from atif import Trajectory
            trajectory = Trajectory.model_validate(json.load(f))
        else:
            print(f"Unsupported source format: {args.from_format}")
            sys.exit(1)

    provider = setup_exporter(endpoint=args.endpoint, console=args.console)
    try:
        project_trajectory(trajectory, privacy_mode=args.privacy)
        exporter = getattr(provider, "asb_otlp_exporter", None)
        if not provider.force_flush(timeout_millis=5000) or (exporter is not None and exporter.failed):
            raise RuntimeError("OTLP exporter did not flush successfully; the trajectory was not modified")
        print(f"Successfully exported trajectory to {args.backend} at {args.endpoint}")
    except (RuntimeError, ValueError) as e:
        print(f"Error exporting trajectory: {e}")
        sys.exit(1)


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

    observe_parser = subparsers.add_parser("observe")
    observe_parser.add_argument(
        "--from", dest="from_format", required=True, choices=["claude-code", "atif"]
    )
    observe_parser.add_argument(
        "--backend", default="phoenix", help="Observability backend (default: phoenix)"
    )
    observe_parser.add_argument(
        "--endpoint", default="http://localhost:6006/v1/traces", help="OTLP HTTP endpoint"
    )
    observe_parser.add_argument(
        "--privacy",
        default="metadata-only",
        choices=["metadata-only", "redacted-content", "full-content"],
    )
    observe_parser.add_argument(
        "--console", action="store_true", help="Also print spans to console"
    )
    observe_parser.add_argument("file")
    observe_parser.set_defaults(func=observe_session)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
