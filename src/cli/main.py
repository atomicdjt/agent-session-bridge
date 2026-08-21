import argparse
import sys

from adapters.antigravity.exporter import export_to_antigravity
from adapters.claude.parser import parse_claude_jsonl
from security.redact import redact_session


def import_session(args):
    with open(args.source, 'r', encoding='utf-8') as f:
        if args.from_format == 'claude-code':
            session = redact_session(parse_claude_jsonl(f))
        else:
            print(f"Unsupported format: {args.from_format}")
            sys.exit(1)
            
    out_data = session.model_dump_json(indent=2)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(out_data)
        print(f"Session imported to {args.output}")
    else:
        print(out_data)
        
    if args.report:
        loss = session.provenance.loss_report
        print("\n--- Preservation Report ---")
        print(f"Turns Preserved:       {loss.turns_preserved}")
        print(f"Tools Preserved:       {loss.tools_preserved}")
        print(f"Unsupported Events:    {loss.unsupported_events}")
        print("---------------------------")

def convert_session(args):
    with open(args.file, 'r', encoding='utf-8') as f:
        if args.from_format == 'claude-code':
            session = redact_session(parse_claude_jsonl(f))
        else:
            print(f"Unsupported source format: {args.from_format}")
            sys.exit(1)
            
    if args.to_format == 'antigravity':
        out_data = export_to_antigravity(session)
    else:
        print(f"Unsupported target format: {args.to_format}")
        sys.exit(1)
        
    print(out_data)

def handoff_session(args):
    print("STATUS: UnsupportedNativeImport")
    print("Reason: Antigravity CLI does not currently expose a supported 'import-session' or public API for writing session state.")
    print("Rule check: Silently mutating the internal `.system_generated` databases is strictly forbidden by the security guidelines.")
    print("Action: Outputting the canonical JSONL payload that would be supplied to an `agy import-session` command once available.")
    print("=" * 80)
    convert_session(args)

def main():
    parser = argparse.ArgumentParser(description="Agent Session Bridge")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    import_p = subparsers.add_parser('import')
    import_p.add_argument('--source', required=True)
    import_p.add_argument('--from', dest='from_format', required=True, choices=['claude-code'])
    import_p.add_argument('--output')
    import_p.add_argument('--report', action='store_true')
    import_p.set_defaults(func=import_session)
    
    convert_p = subparsers.add_parser('convert')
    convert_p.add_argument('--from', dest='from_format', required=True, choices=['claude-code'])
    convert_p.add_argument('--to', dest='to_format', required=True, choices=['antigravity'])
    convert_p.add_argument('file')
    convert_p.set_defaults(func=convert_session)

    handoff_p = subparsers.add_parser('handoff')
    handoff_p.add_argument('--from', dest='from_format', required=True, choices=['claude-code'])
    handoff_p.add_argument('--to', dest='to_format', required=True, choices=['antigravity'])
    handoff_p.add_argument('file')
    handoff_p.set_defaults(func=handoff_session)
    
    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
