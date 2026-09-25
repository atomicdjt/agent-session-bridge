"""Regression coverage for the published real-session fixture.

`fixtures/real-session/` comes from one controlled, real Claude Code session with a
synthetic prompt and synthetic file data; every identifier and path was replaced by the
sanitizer before this file was written. See `fixtures/real-session/README.md` and
`docs/DEMO_REAL_SESSION.md` for what it does and does not demonstrate.
"""

import json
import re
from pathlib import Path

from atif import Trajectory

from adapters.claude.parser import parse_claude_jsonl
from explain import load_manifest, render_report

FIXTURE_DIR = Path("fixtures/real-session")
SOURCE = FIXTURE_DIR / "claude-code-controlled-demo.source.jsonl"
ATIF_DOCUMENT = FIXTURE_DIR / "claude-code-controlled-demo.atif.json"
MANIFEST = FIXTURE_DIR / "claude-code-controlled-demo.manifest.json"

# Forbidden regardless of case; a match here means something private leaked into the
# public fixture or manifest. Kept in sync with the private-review sign-off list.
FORBIDDEN_STRINGS = [
    "C:\\Users", "C:/Users", "Atomic", "David", "Turner", "@gmail",
    "ownerAccountUuid", "ownerOrganizationUuid", "sk-ant-",
    "ANTHROPIC_API_KEY", "Authorization:", "Bearer",
]  # fmt: skip

EXPECTED_TOOLS = sorted(["Read", "Read", "Read", "Bash", "Edit", "Write"])


def _load_atif() -> Trajectory:
    return Trajectory.model_validate(json.loads(ATIF_DOCUMENT.read_text(encoding="utf-8")))


def test_published_atif_document_validates_as_atif_v1_7():
    trajectory = _load_atif()
    assert trajectory.schema_version == "ATIF-v1.7"
    assert trajectory.agent.name == "claude-code"
    assert trajectory.agent.version == "2.1.266"


def test_the_published_source_converts_to_the_published_atif_document():
    with SOURCE.open(encoding="utf-8") as source_file:
        reconverted = parse_claude_jsonl(source_file)
    published = _load_atif()

    assert reconverted.schema_version == published.schema_version
    assert len(reconverted.steps) == len(published.steps)
    assert reconverted.extra is not None and published.extra is not None
    reconverted_fidelity = reconverted.extra["agent_session_bridge"]["fidelity"]
    published_fidelity = published.extra["agent_session_bridge"]["fidelity"]
    volatile = {"transformations"}
    for key in reconverted_fidelity:
        if key not in volatile:
            assert reconverted_fidelity[key] == published_fidelity[key], key


def test_six_tool_calls_correlate_with_six_results_including_the_missing_file_error():
    trajectory = _load_atif()
    calls = [
        (call, step)
        for step in trajectory.steps
        for call in (step.tool_calls or [])
    ]
    assert len(calls) == 6
    assert sorted(call.function_name for call, _ in calls) == EXPECTED_TOOLS

    results_by_call_id: dict[str, list[bool]] = {}
    for step in trajectory.steps:
        for result in (step.observation.results if step.observation else []):
            assert result.source_call_id is not None
            results_by_call_id.setdefault(result.source_call_id, []).append(
                bool((result.extra or {}).get("is_error"))
            )

    call_ids = [call.tool_call_id for call, _ in calls]
    assert len(set(call_ids)) == 6
    assert set(results_by_call_id) == set(call_ids)
    assert all(len(flags) == 1 for flags in results_by_call_id.values())

    error_flags = [flags[0] for flags in results_by_call_id.values()]
    assert error_flags.count(True) == 1

    missing_file_call_id = next(
        call.tool_call_id
        for call, _ in calls
        if call.function_name == "Read" and "missing" in str(call.arguments).lower()
    )
    assert results_by_call_id[missing_file_call_id] == [True]


def test_the_intentional_error_result_text_says_the_file_does_not_exist():
    trajectory = _load_atif()
    error_texts = [
        result.content
        for step in trajectory.steps
        for result in (step.observation.results if step.observation else [])
        if (result.extra or {}).get("is_error")
    ]
    assert len(error_texts) == 1
    assert isinstance(error_texts[0], str) and "does not exist" in error_texts[0].lower()


def test_the_report_is_deterministic_and_uses_the_public_manifest():
    trajectory = _load_atif()
    manifest = load_manifest(MANIFEST)

    first = render_report(trajectory, manifest=manifest)
    second = render_report(_load_atif(), manifest=load_manifest(MANIFEST))
    assert first == second

    assert "### Supplied by the manifest (not verified by this report)" in first
    assert manifest["source_sha256"] in first
    assert "Tool calls: 6 — 5 with a result, 1 with an error result, 0 with no result recorded" in first


def test_manifest_has_exactly_the_approved_public_fields_and_no_raw_hash():
    text = MANIFEST.read_text(encoding="utf-8")
    manifest = json.loads(text)
    assert set(manifest) == {
        "source_sha256", "claude_code_version", "converter_version", "capture_time", "note",
    }  # fmt: skip
    assert manifest["claude_code_version"] == "2.1.266"

    # Exactly one 64-hex-character hash may appear: source_sha256 itself. A second one
    # would be the raw (pre-sanitization) session's hash, which must never be published.
    hashes = re.findall(r"\b[0-9a-fA-F]{64}\b", text)
    assert hashes == [manifest["source_sha256"]]


def test_fixture_and_manifest_contain_none_of_the_forbidden_strings():
    for path in (SOURCE, ATIF_DOCUMENT, MANIFEST):
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        for forbidden in FORBIDDEN_STRINGS:
            assert forbidden.lower() not in lowered, f"{forbidden!r} found in {path}"
