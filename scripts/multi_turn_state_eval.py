from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_CASES_PATH = PROJECT_ROOT / "evals" / "agent" / "multi_turn_cases.json"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "evals" / "reports"


@dataclass(frozen=True)
class MultiTurnSummary:
    total_dialogues: int
    total_turns: int
    pass_rate: float
    intent_accuracy: float
    tool_selection_accuracy: float
    state_match_accuracy: float
    state_inheritance_accuracy: float
    state_override_accuracy: float
    tool_input_consistency: float
    modified_fields_accuracy: float
    invalidated_tools_accuracy: float
    clarification_continuation_pass_rate: float | None
    context_pollution_rate: float | None
    session_isolation_pass_rate: float | None
    category_pass_rate: dict[str, float]


class MetricCounter:
    def __init__(self) -> None:
        self.numerator = 0
        self.denominator = 0

    def add(self, passed: bool) -> None:
        self.denominator += 1
        if passed:
            self.numerator += 1

    def add_many(self, correct: int, total: int) -> None:
        self.numerator += correct
        self.denominator += total

    def ratio(self) -> float | None:
        if self.denominator == 0:
            return None
        return _ratio(self.numerator, self.denominator)


def run_eval(cases_path: Path = DEFAULT_CASES_PATH) -> tuple[MultiTurnSummary, list[dict[str, Any]]]:
    os.environ["AGENT_RUNTIME_MODE"] = "loop"
    os.environ.setdefault("NL_PARSER_MODE", "rule")

    cases = json.loads(cases_path.read_text(encoding="utf-8-sig"))
    results: list[dict[str, Any]] = []

    for case in cases:
        results.extend(run_dialogue_case(case))

    return summarize_results(cases, results), results


def run_dialogue_case(case: dict[str, Any]) -> list[dict[str, Any]]:
    from app.services.session_memory import TTLSessionMemoryStore

    store = TTLSessionMemoryStore()
    previous_state_by_scope: dict[tuple[str, str], dict[str, object]] = {}
    results: list[dict[str, Any]] = []

    for index, turn in enumerate(case.get("turns", []), start=1):
        user_id = str(turn.get("user_id") or case.get("user_id") or "eval-user")
        session_id = str(turn.get("session_id") or case.get("session_id") or f"eval-{case['id']}")
        scope = (user_id, session_id)
        previous_state = dict(previous_state_by_scope.get(scope, {}))
        profile = _build_profile(case.get("profile") or {}, user_id=user_id)
        result = run_turn(
            case=case,
            turn=turn,
            turn_index=index,
            store=store,
            user_id=user_id,
            session_id=session_id,
            profile=profile,
            previous_state=previous_state,
        )
        results.append(result)
        if result["actual_state"]:
            previous_state_by_scope[scope] = result["actual_state"]

    return results


def run_turn(
    *,
    case: dict[str, Any],
    turn: dict[str, Any],
    turn_index: int,
    store: Any,
    user_id: str,
    session_id: str,
    profile: Any,
    previous_state: dict[str, object],
) -> dict[str, Any]:
    from app.agent import initialize_state, mark_parsed, plan_next_step
    from app.agent.context_manager import build_agent_parser_context, build_pending_task_context, merge_agent_context
    from app.services.nl_parser import NaturalLanguageParseError, parse_natural_language_request
    from app.services.session_memory import build_session_context

    session_context = store.get(session_id, user_id=user_id)
    parser_context = build_agent_parser_context(session_context=session_context, profile=profile)
    try:
        parsed_result = parse_natural_language_request(str(turn["input"]), context=parser_context)
        intent = parsed_result.intent
        parsed = parsed_result.parsed
        explicit_missing_fields: list[str] = []
    except NaturalLanguageParseError as exc:
        intent = exc.intent or str(turn.get("expected_intent") or "unknown")
        parsed = {key: value for key, value in exc.parsed.items() if value not in (None, "", [])}
        explicit_missing_fields = list(exc.missing_fields)

    context_result = merge_agent_context(
        intent=intent,
        parsed=parsed,
        session_context=session_context,
        profile=profile,
        missing_fields=explicit_missing_fields,
    )
    state = initialize_state(str(turn["input"]), user_id=user_id, session_id=session_id)
    state = mark_parsed(
        state,
        intent=context_result.intent,
        parsed=context_result.parsed,
        missing_fields=context_result.missing_fields,
    )
    plan = plan_next_step(state)

    action = plan.action.value
    actual_tool = str(plan.tool_name) if plan.tool_name else None
    actual_tool_input = dict(plan.tool_input or {})
    actual_state = dict(context_result.parsed)

    if action == "ask_clarification":
        store.set(
            session_id,
            build_pending_task_context(
                intent=context_result.intent,
                parsed=context_result.parsed,
                missing_fields=context_result.missing_fields,
                query=str(turn["input"]),
            ),
            user_id=user_id,
        )
    elif action == "call_tool":
        store.set(
            session_id,
            build_session_context(context_result.intent, context_result.parsed),
            user_id=user_id,
            title=str(turn["input"])[:80],
        )

    checks = evaluate_turn_checks(
        turn=turn,
        actual_intent=context_result.intent,
        actual_action=action,
        actual_tool=actual_tool,
        actual_state=actual_state,
        actual_tool_input=actual_tool_input,
        previous_state=previous_state,
        modified_fields=context_result.modified_fields,
        invalidated_tools=context_result.invalidated_tools,
        missing_fields=context_result.missing_fields,
    )

    return {
        "case_id": case.get("id"),
        "category": case.get("category"),
        "turn_index": turn_index,
        "user_id": user_id,
        "session_id": session_id,
        "input": turn.get("input"),
        "passed": checks["passed"],
        "checks": checks,
        "expected_intent": turn.get("expected_intent"),
        "actual_intent": context_result.intent,
        "expected_action": turn.get("expected_action"),
        "actual_action": action,
        "expected_tool": turn.get("expected_tool"),
        "actual_tool": actual_tool,
        "expected_state": turn.get("expected_state") or {},
        "actual_state": actual_state,
        "expected_tool_input": _expected_tool_input(turn),
        "actual_tool_input": actual_tool_input,
        "expected_modified_fields": turn.get("expected_modified_fields") or [],
        "actual_modified_fields": context_result.modified_fields,
        "expected_invalidated_tools": turn.get("expected_invalidated_tools") or [],
        "actual_invalidated_tools": context_result.invalidated_tools,
        "expected_missing_fields": turn.get("expected_missing_fields") or [],
        "actual_missing_fields": context_result.missing_fields,
        "field_sources": context_result.field_sources,
        "context_used": context_result.context_used,
        "trace_id": state.trace_id,
    }


def evaluate_turn_checks(
    *,
    turn: dict[str, Any],
    actual_intent: str,
    actual_action: str,
    actual_tool: str | None,
    actual_state: dict[str, object],
    actual_tool_input: dict[str, object],
    previous_state: dict[str, object],
    modified_fields: list[str],
    invalidated_tools: list[str],
    missing_fields: list[str],
) -> dict[str, Any]:
    expected_state = turn.get("expected_state") or {}
    expected_tool_input = _expected_tool_input(turn)
    expected_inherited_fields = [str(item) for item in turn.get("expected_inherited_fields", [])]
    expected_modified_fields = [str(item) for item in turn.get("expected_modified_fields", [])]
    expected_invalidated_tools = [str(item) for item in turn.get("expected_invalidated_tools", [])]
    expected_absent_tool_input_fields = [str(item) for item in turn.get("expected_absent_tool_input_fields", [])]
    expected_missing_fields = [str(item) for item in turn.get("expected_missing_fields", [])]

    state_matches = _field_matches(expected_state, actual_state)
    tool_input_matches = _field_matches(expected_tool_input, actual_tool_input)
    inherited_matches = {
        field: actual_state.get(field) == previous_state.get(field)
        for field in expected_inherited_fields
    }
    override_matches = {
        field: actual_state.get(field) == expected_state.get(field) if field in expected_state else field in modified_fields
        for field in expected_modified_fields
    }
    absent_matches = {
        field: field not in actual_tool_input
        for field in expected_absent_tool_input_fields
    }

    intent_pass = actual_intent == turn.get("expected_intent")
    expected_action = turn.get("expected_action")
    action_pass = True if expected_action is None else actual_action == expected_action
    expected_tool = turn.get("expected_tool")
    tool_pass = True if expected_tool is None else actual_tool == expected_tool
    state_pass = all(state_matches.values())
    tool_input_pass = all(tool_input_matches.values())
    inheritance_pass = all(inherited_matches.values())
    override_pass = all(override_matches.values())
    modified_fields_pass = set(expected_modified_fields).issubset(set(modified_fields))
    invalidated_tools_pass = set(expected_invalidated_tools).issubset(set(invalidated_tools))
    missing_fields_pass = set(expected_missing_fields).issubset(set(missing_fields))
    no_context_pollution = all(absent_matches.values())

    clarification_continuation_pass = None
    if turn.get("expected_continues_after_clarification"):
        clarification_continuation_pass = actual_action == "call_tool" and bool(actual_tool)

    session_isolation_pass = None
    if turn.get("expected_isolation"):
        session_isolation_pass = state_pass and inheritance_pass

    passed = (
        intent_pass
        and action_pass
        and tool_pass
        and state_pass
        and tool_input_pass
        and inheritance_pass
        and override_pass
        and modified_fields_pass
        and invalidated_tools_pass
        and missing_fields_pass
        and no_context_pollution
        and (clarification_continuation_pass is not False)
        and (session_isolation_pass is not False)
    )

    return {
        "passed": passed,
        "intent_pass": intent_pass,
        "action_pass": action_pass,
        "tool_pass": tool_pass,
        "state_pass": state_pass,
        "tool_input_pass": tool_input_pass,
        "inheritance_pass": inheritance_pass,
        "override_pass": override_pass,
        "modified_fields_pass": modified_fields_pass,
        "invalidated_tools_pass": invalidated_tools_pass,
        "missing_fields_pass": missing_fields_pass,
        "no_context_pollution": no_context_pollution,
        "clarification_continuation_pass": clarification_continuation_pass,
        "session_isolation_pass": session_isolation_pass,
        "state_matches": state_matches,
        "tool_input_matches": tool_input_matches,
        "inherited_matches": inherited_matches,
        "override_matches": override_matches,
        "absent_tool_input_matches": absent_matches,
    }


def summarize_results(cases: list[dict[str, Any]], results: list[dict[str, Any]]) -> MultiTurnSummary:
    counters = {
        "intent": MetricCounter(),
        "tool": MetricCounter(),
        "state": MetricCounter(),
        "inheritance": MetricCounter(),
        "override": MetricCounter(),
        "tool_input": MetricCounter(),
        "modified_fields": MetricCounter(),
        "invalidated_tools": MetricCounter(),
        "clarification": MetricCounter(),
        "pollution": MetricCounter(),
        "isolation": MetricCounter(),
    }

    category_counts: dict[str, int] = defaultdict(int)
    category_passes: dict[str, int] = defaultdict(int)

    for result in results:
        checks = result["checks"]
        category = str(result.get("category") or "unknown")
        category_counts[category] += 1
        if result["passed"]:
            category_passes[category] += 1

        counters["intent"].add(checks["intent_pass"])
        counters["tool"].add(checks["tool_pass"])
        counters["state"].add_many(*_count_true(checks["state_matches"]))
        counters["tool_input"].add_many(*_count_true(checks["tool_input_matches"]))
        counters["inheritance"].add_many(*_count_true(checks["inherited_matches"]))
        counters["override"].add_many(*_count_true(checks["override_matches"]))
        if result["expected_modified_fields"]:
            counters["modified_fields"].add(checks["modified_fields_pass"])
        if result["expected_invalidated_tools"]:
            counters["invalidated_tools"].add(checks["invalidated_tools_pass"])
        if checks["clarification_continuation_pass"] is not None:
            counters["clarification"].add(checks["clarification_continuation_pass"])
        if checks["absent_tool_input_matches"]:
            counters["pollution"].add(checks["no_context_pollution"])
        if checks["session_isolation_pass"] is not None:
            counters["isolation"].add(checks["session_isolation_pass"])

    return MultiTurnSummary(
        total_dialogues=len(cases),
        total_turns=len(results),
        pass_rate=_ratio(sum(1 for result in results if result["passed"]), len(results)),
        intent_accuracy=counters["intent"].ratio() or 0.0,
        tool_selection_accuracy=counters["tool"].ratio() or 0.0,
        state_match_accuracy=counters["state"].ratio() or 0.0,
        state_inheritance_accuracy=counters["inheritance"].ratio() or 0.0,
        state_override_accuracy=counters["override"].ratio() or 0.0,
        tool_input_consistency=counters["tool_input"].ratio() or 0.0,
        modified_fields_accuracy=counters["modified_fields"].ratio() or 0.0,
        invalidated_tools_accuracy=counters["invalidated_tools"].ratio() or 0.0,
        clarification_continuation_pass_rate=counters["clarification"].ratio(),
        context_pollution_rate=None
        if counters["pollution"].denominator == 0
        else _ratio(counters["pollution"].denominator - counters["pollution"].numerator, counters["pollution"].denominator),
        session_isolation_pass_rate=counters["isolation"].ratio(),
        category_pass_rate={
            category: _ratio(category_passes[category], count)
            for category, count in sorted(category_counts.items())
        },
    )


def write_reports(
    summary: MultiTurnSummary,
    results: list[dict[str, Any]],
    report_dir: Path = DEFAULT_REPORT_DIR,
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": summary.__dict__,
        "results": results,
    }
    (report_dir / "multi_turn_state_eval.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (report_dir / "multi_turn_state_eval.md").write_text(
        build_markdown_report(summary, results),
        encoding="utf-8",
    )


def build_markdown_report(summary: MultiTurnSummary, results: list[dict[str, Any]]) -> str:
    lines = [
        "# Multi-turn State Eval Report",
        "",
        "## Summary",
        "",
        f"- Total dialogues: {summary.total_dialogues}",
        f"- Total turns: {summary.total_turns}",
        f"- Pass rate: {_pct(summary.pass_rate)}",
        f"- Intent accuracy: {_pct(summary.intent_accuracy)}",
        f"- Tool selection accuracy: {_pct(summary.tool_selection_accuracy)}",
        f"- State match accuracy: {_pct(summary.state_match_accuracy)}",
        f"- State inheritance accuracy: {_pct(summary.state_inheritance_accuracy)}",
        f"- State override accuracy: {_pct(summary.state_override_accuracy)}",
        f"- Tool input consistency: {_pct(summary.tool_input_consistency)}",
        f"- Modified fields accuracy: {_pct(summary.modified_fields_accuracy)}",
        f"- Invalidated tools accuracy: {_pct(summary.invalidated_tools_accuracy)}",
        f"- Clarification continuation pass rate: {_optional_pct(summary.clarification_continuation_pass_rate)}",
        f"- Context pollution rate: {_optional_pct(summary.context_pollution_rate)}",
        f"- Session isolation pass rate: {_optional_pct(summary.session_isolation_pass_rate)}",
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
                f"- {failure['case_id']} turn {failure['turn_index']} ({failure['category']})",
                f"  Input: {failure['input']}",
                f"  Expected intent/tool: {failure['expected_intent']} / {failure['expected_tool']}",
                f"  Actual intent/tool: {failure['actual_intent']} / {failure['actual_tool']}",
                f"  Expected state: {failure['expected_state']}",
                f"  Actual state: {failure['actual_state']}",
                f"  Expected modified fields: {failure['expected_modified_fields']}; actual: {failure['actual_modified_fields']}",
                f"  Expected invalidated tools: {failure['expected_invalidated_tools']}; actual: {failure['actual_invalidated_tools']}",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def _build_profile(profile_data: dict[str, Any], *, user_id: str) -> Any:
    from app.services.profile_memory import ProfileMemory

    return ProfileMemory(
        user_id=user_id,
        default_location=profile_data.get("default_location"),
        default_task_type=profile_data.get("default_task_type"),
        output_style=profile_data.get("output_style"),
    )


def _field_matches(expected: dict[str, Any], actual: dict[str, object]) -> dict[str, bool]:
    return {field: actual.get(field) == expected_value for field, expected_value in expected.items()}


def _expected_tool_input(turn: dict[str, Any]) -> dict[str, Any]:
    if "expected_tool_input" in turn:
        return turn["expected_tool_input"] or {}
    return turn.get("expected_state") or {}


def _count_true(values: dict[str, bool]) -> tuple[int, int]:
    return sum(1 for value in values.values() if value), len(values)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _optional_pct(value: float | None) -> str:
    return "N/A" if value is None else _pct(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run multi-turn state eval for Agent Runtime.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args()

    summary, results = run_eval(args.cases)
    write_reports(summary, results, args.report_dir)
    print(f"Multi-turn State Eval completed: {summary.total_turns} turns, pass_rate={_pct(summary.pass_rate)}")
    print(f"Reports written to: {args.report_dir}")


if __name__ == "__main__":
    main()
