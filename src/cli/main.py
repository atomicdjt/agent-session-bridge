import argparse
import json
import sys
from pathlib import Path

from adapters.antigravity.exporter import export_with_report
from adapters.claude.parser import parse_claude_jsonl
from security.redact import redact_trajectory


def import_session(args: argparse.Namespace) -> None:
    with open(args.source, encoding="utf-8") as source_file:
        trajectory = redact_trajectory(parse_claude_jsonl(source_file))

    output = trajectory.model_dump_json(indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
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


def explain_session(args: argparse.Namespace) -> None:
    from atif import Trajectory
    from pydantic import ValidationError

    from explain import ManifestError, load_manifest, render_report

    try:
        with open(args.file, encoding="utf-8") as atif_file:
            trajectory = Trajectory.model_validate(json.load(atif_file))
        manifest = load_manifest(args.manifest) if args.manifest else None
    except (OSError, json.JSONDecodeError, ValidationError, ManifestError) as error:
        print(f"Cannot explain {args.file}: {error}", file=sys.stderr)
        sys.exit(1)

    report = render_report(trajectory, manifest=manifest, max_chars=args.max_chars)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8", newline="\n")
        print(f"Report written to {args.output}")
    else:
        sys.stdout.buffer.write(report.encode("utf-8"))


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
    if exported.omitted_content_parts:
        print(
            "ASB target-mapping warning: omitted "
            f"{exported.omitted_content_parts} non-text content part(s) because the observed "
            "Antigravity derived-log shape only supports text content.",
            file=sys.stderr,
        )
    print(exported.payload, end="")


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
            trajectory = parse_claude_jsonl(f)
        elif args.from_format == "atif":
            from atif import Trajectory
            trajectory = Trajectory.model_validate(json.load(f))
        else:
            print(f"Unsupported source format: {args.from_format}")
            sys.exit(1)

    if not trajectory.steps:
        print("Error: trajectory contains no valid steps to export.")
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

    explain_parser = subparsers.add_parser(
        "explain", help="Render an ATIF trajectory as a human-readable Markdown report."
    )
    explain_parser.add_argument("file", help="ATIF trajectory JSON, for example from `import`.")
    explain_parser.add_argument(
        "--manifest",
        help="Optional JSON sidecar of source-level facts (source_sha256, claude_code_version, "
        "converter_version, capture_time, note). Shown labelled as unverified.",
    )
    explain_parser.add_argument("--output", help="Write the report here instead of stdout.")
    explain_parser.add_argument(
        "--max-chars",
        type=int,
        default=2000,
        help="Truncate each message, argument, and result to this many characters; 0 shows all.",
    )
    explain_parser.set_defaults(func=explain_session)

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
