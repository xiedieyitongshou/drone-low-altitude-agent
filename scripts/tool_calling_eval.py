from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_CASES_PATH = PROJECT_ROOT / "evals" / "agent" / "cases.json"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "evals" / "reports"

NON_REGISTRY_STEPS = {
    "ask_clarification",
    "parse_task",
    "fetch_weather",
    "merge_context",
}

TOOL_ALIASES = {
    "evaluate_risk": "evaluate_flight_risk",
    "recommend_windows": "recommend_flight_windows",
    "compare_locations": "compare_flight_locations",
    "retrieve_rag_advice": "query_knowledge_snippets",
}

BUSINESS_TOOLS = {
    "evaluate_flight_risk",
    "recommend_flight_windows",
    "compare_flight_locations",
}


@dataclass(frozen=True)
class EvalSummary:
    total_cases: int
    pass_rate: float
    intent_accuracy: float
    tool_selection_accuracy: float
    exact_tool_match_rate: float
    extra_tool_call_rate: float
    missing_tool_call_rate: float
    unexpected_tool_violation_rate: float
    fallback_accuracy: float
    clarification_pass_rate: float | None
    category_pass_rate: dict[str, float]


def normalize_tool_name(tool_name: str) -> str | None:
    normalized = TOOL_ALIASES.get(tool_name, tool_name)
    if normalized in NON_REGISTRY_STEPS:
        return None
    return normalized


def normalize_tool_list(tool_names: list[str]) -> list[str]:
    normalized: list[str] = []
    for tool_name in tool_names:
        item = normalize_tool_name(str(tool_name))
        if item and item not in normalized:
            normalized.append(item)
    return normalized


def extract_actual_tools(response: Any) -> list[str]:
    runtime = getattr(response, "agent_runtime", None) or {}
    runtime_tools = runtime.get("tool_results")
    if isinstance(runtime_tools, list):
        return normalize_tool_list([str(item) for item in runtime_tools])

    result = getattr(response, "result", None) or {}
    if isinstance(result, dict):
        tool_results = result.get("tool_results")
        if isinstance(tool_results, dict):
            return normalize_tool_list([str(item) for item in tool_results.keys()])
        if isinstance(tool_results, list):
            return normalize_tool_list([str(item) for item in tool_results])

    return []


def extract_plan_actions(response: Any) -> list[str]:
    runtime = getattr(response, "agent_runtime", None) or {}
    actions = runtime.get("plan_actions")
    if not isinstance(actions, list):
        return []
    return [str(action) for action in actions]


def extract_missing_fields(response: Any) -> list[str]:
    fallback = getattr(response, "fallback", None)
    if isinstance(fallback, dict):
        missing_fields = fallback.get("missing_fields")
        if isinstance(missing_fields, list):
            return [str(field) for field in missing_fields]
    return []


def extract_actual_fallback(response: Any) -> bool:
    runtime = getattr(response, "agent_runtime", None) or {}
    return bool(getattr(response, "fallback", None)) or not bool(getattr(response, "success", True)) or bool(
        runtime.get("fallback_used")
    )


def evaluate_case(case: dict[str, Any], response: Any) -> dict[str, Any]:
    expected_tools = normalize_tool_list(case.get("expected_tools", []))
    unexpected_tools = normalize_tool_list(case.get("unexpected_tools", []))
    actual_tools = extract_actual_tools(response)
    actual_actions = extract_plan_actions(response)

    expected_tool_set = set(expected_tools)
    actual_tool_set = set(actual_tools)
    unexpected_tool_set = set(unexpected_tools)

    missing_tools = sorted(expected_tool_set - actual_tool_set)
    extra_tools = sorted(actual_tool_set - expected_tool_set)
    unexpected_called = sorted(unexpected_tool_set & actual_tool_set)

    actual_intent = getattr(response, "intent", None)
    expected_intent = case.get("expected_intent")
    expected_fallback = bool(case.get("expected_fallback", False))
    actual_fallback = extract_actual_fallback(response)
    if "ask_clarification" in actual_actions and "fallback" not in actual_actions:
        actual_fallback = False

    expected_missing_fields = [str(field) for field in case.get("expected_missing_fields", [])]
    actual_missing_fields = extract_missing_fields(response)
    needs_clarification = case.get("expected_route") == "clarification" or bool(expected_missing_fields)
    clarification_pass = None
    if needs_clarification:
        clarification_pass = (
            "ask_clarification" in actual_actions
            and not (actual_tool_set & BUSINESS_TOOLS)
            and set(expected_missing_fields).issubset(set(actual_missing_fields))
        )

    checks = {
        "intent_pass": actual_intent == expected_intent,
        "expected_tools_hit": not missing_tools,
        "no_unexpected_tools": not unexpected_called,
        "fallback_pass": expected_fallback == actual_fallback,
        "exact_tool_match": actual_tool_set == expected_tool_set,
        "clarification_pass": clarification_pass,
    }

    passed = (
        checks["intent_pass"]
        and checks["expected_tools_hit"]
        and checks["no_unexpected_tools"]
        and checks["fallback_pass"]
        and (clarification_pass is not False)
    )

    runtime = getattr(response, "agent_runtime", None) or {}
    return {
        "case_id": case.get("id"),
        "category": case.get("category"),
        "passed": passed,
        "checks": checks,
        "expected_intent": expected_intent,
        "actual_intent": actual_intent,
        "expected_tools": expected_tools,
        "actual_tools": actual_tools,
        "unexpected_tools": unexpected_tools,
        "missing_tools": missing_tools,
        "extra_tools": extra_tools,
        "unexpected_called": unexpected_called,
        "expected_fallback": expected_fallback,
        "actual_fallback": actual_fallback,
        "expected_missing_fields": expected_missing_fields,
        "actual_missing_fields": actual_missing_fields,
        "plan_actions": actual_actions,
        "trace_id": runtime.get("trace_id"),
    }


def summarize_results(results: list[dict[str, Any]]) -> EvalSummary:
    total = len(results)
    if total == 0:
        return EvalSummary(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, None, {})

    expected_tool_total = sum(len(result["expected_tools"]) for result in results)
    missing_tool_total = sum(len(result["missing_tools"]) for result in results)
    unexpected_tool_total = sum(len(result["unexpected_tools"]) for result in results)
    unexpected_called_total = sum(len(result["unexpected_called"]) for result in results)

    category_counts: dict[str, int] = defaultdict(int)
    category_passes: dict[str, int] = defaultdict(int)
    for result in results:
        category = str(result.get("category") or "unknown")
        category_counts[category] += 1
        if result["passed"]:
            category_passes[category] += 1

    clarification_results = [
        result for result in results if result["checks"].get("clarification_pass") is not None
    ]

    return EvalSummary(
        total_cases=total,
        pass_rate=_ratio(sum(1 for result in results if result["passed"]), total),
        intent_accuracy=_ratio(sum(1 for result in results if result["checks"]["intent_pass"]), total),
        tool_selection_accuracy=_ratio(sum(1 for result in results if result["checks"]["expected_tools_hit"]), total),
        exact_tool_match_rate=_ratio(sum(1 for result in results if result["checks"]["exact_tool_match"]), total),
        extra_tool_call_rate=_ratio(sum(1 for result in results if result["extra_tools"]), total),
        missing_tool_call_rate=_ratio(missing_tool_total, expected_tool_total),
        unexpected_tool_violation_rate=_ratio(unexpected_called_total, unexpected_tool_total),
        fallback_accuracy=_ratio(sum(1 for result in results if result["checks"]["fallback_pass"]), total),
        clarification_pass_rate=None
        if not clarification_results
        else _ratio(
            sum(1 for result in clarification_results if result["checks"]["clarification_pass"]),
            len(clarification_results),
        ),
        category_pass_rate={
            category: _ratio(category_passes[category], count)
            for category, count in sorted(category_counts.items())
        },
    )


def run_eval(cases_path: Path = DEFAULT_CASES_PATH, *, execute_tools: bool = False) -> tuple[EvalSummary, list[dict[str, Any]]]:
    os.environ["AGENT_RUNTIME_MODE"] = "loop"
    os.environ.setdefault("NL_PARSER_MODE", "rule")

    cases = json.loads(cases_path.read_text(encoding="utf-8-sig"))
    results: list[dict[str, Any]] = []

    if execute_tools:
        from app.services.task_orchestrator import orchestrate_task_query

        for case in cases:
            response = _run_orchestrator_case(case, orchestrate_task_query)
            results.append(evaluate_case(case, response))
        return summarize_results(results), results

    from app.services.session_memory import TTLSessionMemoryStore

    store = TTLSessionMemoryStore()
    for case in cases:
        _seed_history_state(case, store)
        response = _run_planner_case(case, store)
        results.append(evaluate_case(case, response))

    return summarize_results(results), results


def _run_orchestrator_case(case: dict[str, Any], orchestrate_task_query: Any) -> Any:
    history_state = case.get("history_state") or {}
    return orchestrate_task_query(
        case["input"],
        session_id=history_state.get("session_id") or f"eval-{case['id']}",
        user_id=history_state.get("user_id") or "eval-user",
    )


def _seed_history_state(case: dict[str, Any], store: Any) -> None:
    history_state = case.get("history_state") or {}
    session_id = history_state.get("session_id") or f"eval-{case['id']}"
    user_id = history_state.get("user_id") or "eval-user"

    pending_task = history_state.get("pending_task")
    if isinstance(pending_task, dict):
        payload = {"intent": history_state.get("previous_intent") or case.get("expected_intent"), **pending_task}
        store.set(session_id, payload, user_id=user_id)


def _run_planner_case(case: dict[str, Any], store: Any) -> Any:
    from app.agent import initialize_state, mark_parsed, plan_next_step
    from app.services.nl_parser import NaturalLanguageParseError, parse_natural_language_request

    history_state = case.get("history_state") or {}
    session_id = history_state.get("session_id") or f"eval-{case['id']}"
    user_id = history_state.get("user_id") or "eval-user"
    context = store.get(session_id, user_id=user_id)

    try:
        parsed_result = parse_natural_language_request(case["input"], context=context)
        intent = parsed_result.intent
        parsed = parsed_result.parsed
        missing_fields: list[str] = []
    except NaturalLanguageParseError as exc:
        intent = exc.intent or case.get("expected_intent") or "unknown"
        parsed = {key: value for key, value in exc.parsed.items() if value not in (None, "", [])}
        missing_fields = exc.missing_fields

    state = initialize_state(case["input"], user_id=user_id, session_id=session_id)
    state = mark_parsed(state, intent=intent, parsed=parsed, missing_fields=missing_fields)
    plan = plan_next_step(state)

    if history_state.get("force_tool_error"):
        return SimpleNamespace(
            intent=intent,
            success=False,
            fallback={
                "error_type": "external_service_error",
                "reason": str(history_state["force_tool_error"]),
            },
            result={"tool_results": {}},
            agent_runtime={
                "mode": "planner_only",
                "trace_id": state.trace_id,
                "run_id": state.run_id,
                "status": "failed",
                "fallback_used": True,
                "plan_actions": ["call_tool", "fallback"],
                "tool_results": [],
                "errors": [str(history_state["force_tool_error"])],
            },
        )

    actual_tools = [str(plan.tool_name)] if plan.tool_name else []
    fallback = None
    success = True
    if plan.action.value == "ask_clarification":
        fallback = {"missing_fields": plan.missing_fields}
        success = False
    elif plan.action.value == "fallback":
        fallback = {"reason": plan.reason}
        success = False

    return SimpleNamespace(
        intent=intent,
        success=success,
        fallback=fallback,
        result={"tool_results": {tool: {"success": True} for tool in actual_tools}},
        agent_runtime={
            "mode": "planner_only",
            "trace_id": state.trace_id,
            "run_id": state.run_id,
            "status": "planned",
            "fallback_used": plan.action.value == "fallback",
            "plan_actions": [plan.action.value],
            "tool_results": actual_tools,
            "errors": [],
        },
    )


def _run_with_planner_only(self: Any, state: Any, context: Any) -> Any:
    from app.agent import (
        AgentLoopResult,
        AgentPlanAction,
        ToolResult,
        build_agent_fallback_output,
        build_clarification_message,
        mark_completed,
        mark_needs_clarification,
        plan_next_step,
        record_tool_result,
    )

    plan = plan_next_step(state)
    if plan.action == AgentPlanAction.ASK_CLARIFICATION:
        message = build_clarification_message(plan.missing_fields)
        clarified = mark_needs_clarification(state, plan.missing_fields, message=message)
        return AgentLoopResult(
            success=True,
            final_state=clarified,
            message=message,
            output=build_agent_fallback_output(state=clarified, message=message),
            requires_clarification=True,
            last_plan=plan,
            plans=[plan],
        )

    if plan.action == AgentPlanAction.CALL_TOOL:
        tool_result = ToolResult(
            success=True,
            tool_name=str(plan.tool_name),
            data={
                "tool_name": plan.tool_name,
                "tool_input": plan.tool_input,
                "metadata": plan.metadata,
            },
        )
        completed = record_tool_result(state, tool_name=str(plan.tool_name), tool_result=tool_result)
        completed = mark_completed(completed, message="planner-only eval completed")
        return AgentLoopResult(
            success=True,
            final_state=completed,
            message="planner-only eval completed",
            output={
                "tool_results": {
                    str(plan.tool_name): tool_result.model_dump(mode="json"),
                }
            },
            last_plan=plan,
            plans=[plan],
        )

    completed = mark_completed(state, message=plan.reason)
    return AgentLoopResult(
        success=True,
        final_state=completed,
        message=plan.reason,
        output={},
        last_plan=plan,
        plans=[plan],
    )


def write_reports(summary: EvalSummary, results: list[dict[str, Any]], report_dir: Path = DEFAULT_REPORT_DIR) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": summary.__dict__,
        "results": results,
    }
    (report_dir / "tool_calling_eval.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (report_dir / "tool_calling_eval.md").write_text(
        build_markdown_report(summary, results),
        encoding="utf-8",
    )


def build_markdown_report(summary: EvalSummary, results: list[dict[str, Any]]) -> str:
    lines = [
        "# Tool Calling Eval Report",
        "",
        "## Summary",
        "",
        f"- Total cases: {summary.total_cases}",
        f"- Pass rate: {_pct(summary.pass_rate)}",
        f"- Intent accuracy: {_pct(summary.intent_accuracy)}",
        f"- Tool selection accuracy: {_pct(summary.tool_selection_accuracy)}",
        f"- Exact tool match rate: {_pct(summary.exact_tool_match_rate)}",
        f"- Extra tool call rate: {_pct(summary.extra_tool_call_rate)}",
        f"- Missing tool call rate: {_pct(summary.missing_tool_call_rate)}",
        f"- Unexpected tool violation rate: {_pct(summary.unexpected_tool_violation_rate)}",
        f"- Fallback accuracy: {_pct(summary.fallback_accuracy)}",
        f"- Clarification pass rate: {'N/A' if summary.clarification_pass_rate is None else _pct(summary.clarification_pass_rate)}",
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
        lines.extend(
            [
                f"- {failure['case_id']} ({failure['category']})",
                f"  Expected intent: {failure['expected_intent']}; actual intent: {failure['actual_intent']}",
                f"  Expected tools: {failure['expected_tools']}; actual tools: {failure['actual_tools']}",
                f"  Missing tools: {failure['missing_tools']}; unexpected called: {failure['unexpected_called']}",
                f"  Plan actions: {failure['plan_actions']}; trace_id: {failure['trace_id']}",
            ]
        )

    lines.append("")
    return "\n".join(lines)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Tool Calling Eval for Agent Runtime.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument(
        "--execute-tools",
        action="store_true",
        help="Execute real registered tools. Default is planner-only to avoid external service calls.",
    )
    args = parser.parse_args()

    summary, results = run_eval(args.cases, execute_tools=args.execute_tools)
    write_reports(summary, results, args.report_dir)
    print(f"Tool Calling Eval completed: {summary.total_cases} cases, pass_rate={_pct(summary.pass_rate)}")
    print(f"Reports written to: {args.report_dir}")


if __name__ == "__main__":
    main()
