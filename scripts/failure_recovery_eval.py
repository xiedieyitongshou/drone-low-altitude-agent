from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_CASES_PATH = PROJECT_ROOT / "evals" / "agent" / "failure_recovery_cases.json"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "evals" / "reports"

FABRICATION_TERMS = ["适飞", "禁飞", "风险较低", "可以执行"]


@dataclass(frozen=True)
class FailureRecoverySummary:
    total_cases: int
    pass_rate: float
    failure_classification_accuracy: float
    recovery_action_accuracy: float
    fallback_decision_accuracy: float
    retryability_accuracy: float
    no_fabrication_pass_rate: float
    user_message_quality_pass_rate: float
    trace_error_coverage: float
    trace_tool_coverage: float
    structured_error_completeness: float
    permission_bypass_rate: float | None
    category_pass_rate: dict[str, float]


def run_eval(cases_path: Path = DEFAULT_CASES_PATH) -> tuple[FailureRecoverySummary, list[dict[str, Any]]]:
    cases = json.loads(cases_path.read_text(encoding="utf-8-sig"))
    results = [run_failure_case(case) for case in cases]
    return summarize_results(results), results


def run_failure_case(case: dict[str, Any]) -> dict[str, Any]:
    from app.agent import AgentLoop, ToolExecutionContext, ToolExecutor, initialize_state, mark_parsed

    trace_events = []
    registry = build_failure_registry(case)
    executor = ToolExecutor(tool_registry=registry, trace_recorder=trace_events.append)
    state = initialize_state(
        f"eval:{case['id']}",
        user_id=(case.get("context") or {}).get("user_id"),
        session_id=f"failure-{case['id']}",
    )
    state = mark_parsed(state, intent=str(case["intent"]), parsed=case.get("parsed") or {})

    def fallback_handler(_, __):
        return {"source": "failure_recovery_eval"}

    context_data = case.get("context") or {}
    result = AgentLoop(
        tool_registry=registry,
        tool_executor=executor,
        fallback_handler=fallback_handler,
    ).run(
        state,
        context=ToolExecutionContext(
            user_id=context_data.get("user_id"),
            tenant_id=context_data.get("tenant_id") or "public",
            role=context_data.get("role") or "user",
        ),
    )

    output = result.output if isinstance(result.output, dict) else {}
    latest_error = result.final_state.errors[-1] if result.final_state.errors else {}
    actual = {
        "success": result.success,
        "failure_type": output.get("failure_type"),
        "recovery_action": output.get("recovery_action"),
        "retryable": output.get("retryable"),
        "fallback_used": result.fallback_used or bool(output.get("fallback_used")),
        "error_code": latest_error.get("error_code") or output.get("error_code"),
        "message": result.message,
        "output": output,
        "trace_event_types": [event.event_type.value for event in trace_events],
        "trace_error_codes": [event.error_code for event in trace_events if event.error_code],
    }
    checks = evaluate_failure_checks(case, actual)
    return {
        "case_id": case.get("id"),
        "category": case.get("category"),
        "passed": checks["passed"],
        "checks": checks,
        "expected": case.get("expected") or {},
        "actual": actual,
        "trace_events": [event.model_dump(mode="json") for event in trace_events],
    }


def build_failure_registry(case: dict[str, Any]) -> Any:
    from app.agent import ToolRegistry, ToolSpec

    failure = case.get("failure") or {}
    tool_name = str(case["tool_name"])
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name=tool_name,
            description=f"Failure recovery eval fake tool: {tool_name}",
            side_effect=_side_effect_for_tool(tool_name),
            risk_level="high" if tool_name in {"evaluate_flight_risk", "recommend_flight_windows", "compare_flight_locations"} else "low",
            requires_auth=bool(failure.get("requires_auth", True)),
            requires_admin=bool(failure.get("requires_admin", False)),
        ),
        build_failure_handler(failure),
    )
    return registry


def build_failure_handler(failure: dict[str, Any]):
    if failure.get("mode") != "raise":
        return lambda payload, context: {"ok": True}

    exception_name = str(failure.get("exception") or "RuntimeError")
    message = str(failure.get("message") or exception_name)
    exception_type = {
        "TimeoutError": TimeoutError,
        "ConnectionError": ConnectionError,
        "RuntimeError": RuntimeError,
        "ValueError": ValueError,
        "KeyError": KeyError,
    }.get(exception_name, RuntimeError)

    def handler(payload, context):
        raise exception_type(message)

    return handler


def evaluate_failure_checks(case: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    expected = case.get("expected") or {}
    message = str(actual.get("message") or "")
    output_text = json.dumps(actual.get("output") or {}, ensure_ascii=False)
    combined_text = f"{message}\n{output_text}"

    trace_event_types = set(actual.get("trace_event_types") or [])
    expected_trace_event_types = set(expected.get("trace_event_types") or [])
    missing_trace_events = sorted(expected_trace_event_types - trace_event_types)

    structured_fields = expected.get("structured_error_fields") or []
    missing_structured_fields = [
        field for field in structured_fields if field not in (actual.get("output") or {})
    ]

    permission_bypass_pass = True
    if "permission" in str(case.get("category")):
        permission_bypass_pass = not bool(expected.get("permission_bypass", False)) and not bool(actual.get("fallback_used"))

    checks = {
        "success_pass": actual.get("success") == expected.get("success"),
        "failure_type_pass": actual.get("failure_type") == expected.get("failure_type"),
        "recovery_action_pass": actual.get("recovery_action") == expected.get("recovery_action"),
        "retryable_pass": actual.get("retryable") == expected.get("retryable"),
        "fallback_decision_pass": actual.get("fallback_used") == expected.get("fallback_used"),
        "error_code_pass": actual.get("error_code") == expected.get("error_code"),
        "message_keywords_pass": all(keyword in combined_text for keyword in expected.get("message_keywords", [])),
        "no_fabrication_pass": not any(term in combined_text for term in FABRICATION_TERMS)
        if expected.get("no_fabrication", True)
        else True,
        "trace_event_pass": not missing_trace_events,
        "trace_error_pass": "error" in trace_event_types,
        "trace_tool_pass": "tool_call" in trace_event_types,
        "structured_error_pass": not missing_structured_fields,
        "permission_bypass_pass": permission_bypass_pass,
        "missing_trace_events": missing_trace_events,
        "missing_structured_fields": missing_structured_fields,
    }
    checks["passed"] = all(
        checks[key]
        for key in [
            "success_pass",
            "failure_type_pass",
            "recovery_action_pass",
            "retryable_pass",
            "fallback_decision_pass",
            "error_code_pass",
            "message_keywords_pass",
            "no_fabrication_pass",
            "trace_event_pass",
            "trace_error_pass",
            "trace_tool_pass",
            "structured_error_pass",
            "permission_bypass_pass",
        ]
    )
    return checks


def summarize_results(results: list[dict[str, Any]]) -> FailureRecoverySummary:
    total = len(results)
    permission_results = [result for result in results if "permission" in str(result.get("category"))]
    category_counts: dict[str, int] = defaultdict(int)
    category_passes: dict[str, int] = defaultdict(int)
    for result in results:
        category = str(result.get("category") or "unknown")
        category_counts[category] += 1
        if result["passed"]:
            category_passes[category] += 1

    return FailureRecoverySummary(
        total_cases=total,
        pass_rate=_case_ratio(results, "passed"),
        failure_classification_accuracy=_check_ratio(results, "failure_type_pass"),
        recovery_action_accuracy=_check_ratio(results, "recovery_action_pass"),
        fallback_decision_accuracy=_check_ratio(results, "fallback_decision_pass"),
        retryability_accuracy=_check_ratio(results, "retryable_pass"),
        no_fabrication_pass_rate=_check_ratio(results, "no_fabrication_pass"),
        user_message_quality_pass_rate=_check_ratio(results, "message_keywords_pass"),
        trace_error_coverage=_check_ratio(results, "trace_error_pass"),
        trace_tool_coverage=_check_ratio(results, "trace_tool_pass"),
        structured_error_completeness=_check_ratio(results, "structured_error_pass"),
        permission_bypass_rate=None
        if not permission_results
        else _ratio(
            sum(1 for result in permission_results if not result["checks"]["permission_bypass_pass"]),
            len(permission_results),
        ),
        category_pass_rate={
            category: _ratio(category_passes[category], count)
            for category, count in sorted(category_counts.items())
        },
    )


def write_reports(
    summary: FailureRecoverySummary,
    results: list[dict[str, Any]],
    report_dir: Path = DEFAULT_REPORT_DIR,
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": summary.__dict__,
        "results": results,
    }
    (report_dir / "failure_recovery_eval.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (report_dir / "failure_recovery_eval.md").write_text(
        build_markdown_report(summary, results),
        encoding="utf-8",
    )


def build_markdown_report(summary: FailureRecoverySummary, results: list[dict[str, Any]]) -> str:
    lines = [
        "# Failure Recovery Eval Report",
        "",
        "## Summary",
        "",
        f"- Total cases: {summary.total_cases}",
        f"- Pass rate: {_pct(summary.pass_rate)}",
        f"- Failure classification accuracy: {_pct(summary.failure_classification_accuracy)}",
        f"- Recovery action accuracy: {_pct(summary.recovery_action_accuracy)}",
        f"- Fallback decision accuracy: {_pct(summary.fallback_decision_accuracy)}",
        f"- Retryability accuracy: {_pct(summary.retryability_accuracy)}",
        f"- No fabrication pass rate: {_pct(summary.no_fabrication_pass_rate)}",
        f"- User message quality pass rate: {_pct(summary.user_message_quality_pass_rate)}",
        f"- Trace error coverage: {_pct(summary.trace_error_coverage)}",
        f"- Trace tool coverage: {_pct(summary.trace_tool_coverage)}",
        f"- Structured error completeness: {_pct(summary.structured_error_completeness)}",
        f"- Permission bypass rate: {_optional_pct(summary.permission_bypass_rate)}",
        "",
        "## Category Pass Rate",
        "",
    ]
    for category, value in summary.category_pass_rate.items():
        lines.append(f"- {category}: {_pct(value)}")

    failures = [result for result in results if not result["passed"]]
    lines.extend(["", "## Failures", ""])
    if not failures:
        lines.append("- None")
    for failure in failures:
        actual = failure["actual"]
        expected = failure["expected"]
        lines.extend(
            [
                f"- {failure['case_id']} ({failure['category']})",
                f"  Expected failure/recovery: {expected.get('failure_type')} / {expected.get('recovery_action')}",
                f"  Actual failure/recovery: {actual.get('failure_type')} / {actual.get('recovery_action')}",
                f"  Expected fallback_used: {expected.get('fallback_used')}; actual: {actual.get('fallback_used')}",
                f"  Trace events: {actual.get('trace_event_types')}",
                f"  Checks: {failure['checks']}",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def _side_effect_for_tool(tool_name: str) -> str:
    if tool_name in {"query_user_history", "query_knowledge_snippets", "explain_risk_rules"}:
        return "read_only"
    return "compute_only"


def _case_ratio(results: list[dict[str, Any]], field: str) -> float:
    return _ratio(sum(1 for result in results if result.get(field)), len(results))


def _check_ratio(results: list[dict[str, Any]], field: str) -> float:
    return _ratio(sum(1 for result in results if result["checks"].get(field)), len(results))


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _optional_pct(value: float | None) -> str:
    return "N/A" if value is None else _pct(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run failure recovery eval for Agent Runtime.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args()

    summary, results = run_eval(args.cases)
    write_reports(summary, results, args.report_dir)
    print(f"Failure Recovery Eval completed: {summary.total_cases} cases, pass_rate={_pct(summary.pass_rate)}")
    print(f"Reports written to: {args.report_dir}")


if __name__ == "__main__":
    main()
