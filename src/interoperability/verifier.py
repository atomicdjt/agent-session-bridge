from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atif import Trajectory
from pydantic import ValidationError


@dataclass(frozen=True)
class Finding:
    name: str
    state: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "state": self.state, "detail": self.detail}


def verify_files(
    source_path: Path, output_path: Path, oracle_path: Path, *, implementation: str = "asb"
) -> dict[str, Any]:
    oracle = _read_json(oracle_path)
    source_records = _read_source(source_path)
    output_document = _read_json(output_path)
    findings = _verify_document(source_records, output_document, oracle, implementation)
    conflicts = [finding for finding in findings if finding.state == "CONFLICT"]
    return {
        "schema_version": "ASB-interoperability-report-v1",
        "implementation": implementation,
        "source": str(source_path),
        "output": str(output_path),
        "oracle": str(oracle_path),
        "summary": {
            "passed": not conflicts,
            "findings": len(findings),
            "conflicts": len(conflicts),
        },
        "findings": [finding.as_dict() for finding in findings],
    }


def _verify_document(
    source_records: list[dict[str, Any]],
    output_document: dict[str, Any],
    oracle: dict[str, Any],
    implementation: str,
) -> list[Finding]:
    findings: list[Finding] = []
    try:
        trajectory = Trajectory.model_validate(output_document)
    except (TypeError, ValidationError) as error:
        return [Finding("atif_validation", "CONFLICT", str(error))]

    source_facts = oracle["source_facts"]
    output_steps = trajectory.steps
    findings.append(
        _match(
            "source_timestamps",
            source_facts["source_timestamps"],
            [record.get("timestamp") for record in source_records],
            "PRESERVED",
            "timestamps present in the source fixture",
        )
    )
    source_calls = [
        {
            "id": block.get("id"),
            "name": block.get("name"),
            "arguments": block.get("input"),
        }
        for record in source_records
        for block in _content_blocks(record, "assistant")
        if block.get("type") == "tool_use"
    ]
    findings.append(
        _match(
            "source_tool_calls",
            source_facts["tool_calls"],
            source_calls,
            "PRESERVED",
            "tool calls declared by the source fixture",
            canonical=True,
            report_expected=_apply_redaction_policy(source_facts["tool_calls"], oracle),
            report_actual=_apply_redaction_policy(source_calls, oracle),
        )
    )
    source_result_ids = [
        block.get("tool_use_id")
        for record in source_records
        for block in _content_blocks(record, "user")
        if block.get("type") == "tool_result"
    ]
    findings.append(
        _match(
            "source_tool_result_ids",
            [result["call_id"] for result in source_facts["tool_results"]],
            source_result_ids,
            "PRESERVED",
            "tool-result IDs declared by the source fixture",
        )
    )
    expected_roles = source_facts["output_step_sequence"]
    actual_roles = [step.source for step in output_steps]
    findings.append(
        _match("step_roles", expected_roles, actual_roles, "PRESERVED", "step role sequence")
    )
    findings.append(
        _match(
            "step_timestamps",
            source_facts["output_step_timestamps"],
            [step.timestamp for step in output_steps],
            "PRESERVED",
            "emitted step timestamps",
        )
    )
    findings.append(
        _match(
            "step_text",
            source_facts["output_step_text"],
            [step.message for step in output_steps],
            "PRESERVED",
            "emitted step text",
        )
    )

    actual_calls = [
        {
            "id": call.tool_call_id,
            "name": call.function_name,
            "arguments": call.arguments,
        }
        for step in output_steps
        for call in step.tool_calls or []
    ]
    expected_calls = source_facts["tool_calls"]
    if implementation == "asb":
        expected_calls = _apply_redaction_policy(expected_calls, oracle)
    findings.append(
        _match(
            "tool_calls",
            expected_calls,
            actual_calls,
            "PRESERVED",
            "tool-call IDs, names, and canonical arguments",
            canonical=True,
            report_expected=_apply_redaction_policy(source_facts["tool_calls"], oracle),
            report_actual=_apply_redaction_policy(actual_calls, oracle),
        )
    )

    actual_results: dict[str, list[Any]] = {}
    for step in output_steps:
        for result in (step.observation.results if step.observation else []):
            if result.source_call_id is not None:
                actual_results.setdefault(result.source_call_id, []).append(result.content)
    expected_results: dict[str, Any] = {
        result["call_id"]: result["normalized_content"]
        for result in source_facts["tool_results"]
    }
    if implementation == "asb":
        expected_results = _apply_redaction_policy(expected_results, oracle)
    actual_result_map = {
        call_id: values[0] if len(values) == 1 else values
        for call_id, values in actual_results.items()
    }
    findings.append(
        _match_result_map(expected_results, actual_result_map, implementation, oracle)
    )

    unsupported_record_count = len(oracle["source_facts"]["unsupported_source_records"])
    unsupported_block_count = len(oracle["source_facts"]["unsupported_source_blocks"])
    fidelity = _fidelity(output_document)
    expected_fidelity = oracle["asb_policy"]["expected_fidelity"]
    if implementation == "asb":
        findings.append(
            _match(
                "fidelity_accounting",
                expected_fidelity,
                {key: fidelity.get(key) for key in expected_fidelity},
                "PRESERVED",
                "ASB fidelity report",
            )
        )
        findings.append(
            _match(
                "unsupported_material_is_accounted_for",
                {
                    "records": unsupported_record_count,
                    "blocks": unsupported_block_count,
                },
                {
                    "records": fidelity.get("unsupported_source_records"),
                    "blocks": fidelity.get("unsupported_source_blocks"),
                },
                "DEGRADED",
                "unsupported source material is not falsely marked preserved",
            )
        )
        findings.append(_redaction_finding(output_document, oracle))
        findings.append(_session_finding(trajectory.session_id, source_facts["session_id"]))
        findings.append(_ignored_field_finding(output_document, source_records, source_facts))
    else:
        findings.append(
            Finding(
                "peer_specific_fidelity_and_redaction",
                "NOT_APPLICABLE",
                "ASB policy fields are not imposed on an independent implementation.",
            )
        )

    findings.append(
        Finding(
            "tool_result_timestamps",
            "OMITTED",
            "Source result timestamps are known but ATIF-v1.7 ObservationResult has no timestamp field; no timestamp was fabricated.",
        )
    )
    findings.append(
        _match(
            "unsupported_source_record_is_omitted",
            unsupported_record_count,
            fidelity.get("unsupported_source_records")
            if implementation == "asb"
            else unsupported_record_count,
            "OMITTED",
            "fixture includes intentionally unsupported records",
        )
    )
    return findings


def _match(
    name: str,
    expected: Any,
    actual: Any,
    success_state: str,
    detail: str,
    *,
    canonical: bool = False,
    report_expected: Any | None = None,
    report_actual: Any | None = None,
) -> Finding:
    if canonical:
        expected = _canonical(expected)
        actual = _canonical(actual)
    state = success_state if expected == actual else "CONFLICT"
    shown_expected = expected if report_expected is None else report_expected
    shown_actual = actual if report_actual is None else report_actual
    if canonical:
        shown_expected = _canonical(shown_expected)
        shown_actual = _canonical(shown_actual)
    return Finding(
        name,
        state,
        f"expected={shown_expected!r}; actual={shown_actual!r}; {detail}",
    )


def _match_result_map(
    expected: dict[str, Any],
    actual: dict[str, Any],
    implementation: str,
    oracle: dict[str, Any],
) -> Finding:
    if implementation != "asb":
        expected = {
            call_id: _canonical_result(value) for call_id, value in expected.items()
        }
        actual = {
            call_id: _canonical_result(value) for call_id, value in actual.items()
        }
    state = "NORMALIZED" if expected == actual else "CONFLICT"
    return Finding(
        "tool_result_correlation",
        state,
        "expected="
        f"{_canonical(_apply_redaction_policy(expected, oracle))!r}; "
        f"actual={_canonical(_apply_redaction_policy(actual, oracle))!r}; "
        "later tool results attached to their originating calls",
    )


def _canonical_result(value: Any) -> Any:
    if isinstance(value, list):
        return [_canonical_result(item) for item in value]
    if not isinstance(value, str):
        return value
    try:
        return json.dumps(json.loads(value), sort_keys=True, separators=(",", ":"))
    except json.JSONDecodeError:
        normalized = value.replace("\r\n", "\n")
        while "\n\n" in normalized:
            normalized = normalized.replace("\n\n", "\n")
        return normalized.rstrip()


def _redaction_finding(output_document: dict[str, Any], oracle: dict[str, Any]) -> Finding:
    serialized = json.dumps(output_document, ensure_ascii=False, sort_keys=True)
    expectations = oracle["asb_policy"]["redaction_expectations"]
    sentinel = oracle["asb_policy"]["redaction_sentinel"]
    if any(expectation["source_value"] in serialized for expectation in expectations):
        return Finding("secret_redaction", "CONFLICT", "synthetic secret-like value survived")
    if sentinel not in serialized:
        return Finding("secret_redaction", "CONFLICT", "redaction sentinel is absent")
    workspace = output_document.get("extra", {}).get("agent_session_bridge", {}).get(
        "workspace", {}
    )
    if "cwd" in workspace:
        return Finding("secret_redaction", "CONFLICT", "workspace cwd survived ASB redaction")
    return Finding("secret_redaction", "PRESERVED", "synthetic secret-like values were redacted")


def _apply_redaction_policy(value: Any, oracle: dict[str, Any]) -> Any:
    expectations = oracle["asb_policy"]["redaction_expectations"]
    if isinstance(value, str):
        for expectation in expectations:
            value = value.replace(expectation["source_value"], expectation["replacement"])
        return value
    if isinstance(value, list):
        return [_apply_redaction_policy(item, oracle) for item in value]
    if isinstance(value, dict):
        return {
            key: _apply_redaction_policy(item, oracle) for key, item in value.items()
        }
    return value


def _session_finding(actual: str | None, expected: str) -> Finding:
    return _match("session_identity", expected, actual, "PRESERVED", "source session ID")


def _ignored_field_finding(
    output_document: dict[str, Any],
    source_records: list[dict[str, Any]],
    source_facts: dict[str, Any],
) -> Finding:
    ignored = source_facts["ignored_source_fields"][0]
    serialized = json.dumps(output_document, ensure_ascii=False)
    if ignored["value"] in serialized:
        return Finding("ignored_source_field", "CONFLICT", "ignored field value leaked into output")
    if source_records[ignored["record"] - 1].get(ignored["field"]) != ignored["value"]:
        return Finding("ignored_source_field", "CONFLICT", "oracle does not match source fixture")
    return Finding("ignored_source_field", "OMITTED", "provider-only debug field was intentionally omitted")


def _fidelity(document: dict[str, Any]) -> dict[str, Any]:
    return document.get("extra", {}).get("agent_session_bridge", {}).get("fidelity", {})


def _content_blocks(record: dict[str, Any], role: str) -> list[dict[str, Any]]:
    message = record.get("message")
    if not isinstance(message, dict) or message.get("role", record.get("type")) != role:
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def _read_source(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if isinstance(value, dict):
                records.append(value)
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify ASB semantic interoperability fixtures")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--implementation", default="asb")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    report = verify_files(args.source, args.output, args.oracle, implementation=args.implementation)
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.report:
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["summary"]["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
