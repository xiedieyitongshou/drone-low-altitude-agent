from types import SimpleNamespace

from scripts.tool_calling_eval import evaluate_case, normalize_tool_list, summarize_results


def _response(
    *,
    intent="evaluate",
    tools=None,
    actions=None,
    success=True,
    fallback=None,
    missing_fields=None,
):
    fallback_payload = fallback
    if missing_fields is not None:
        fallback_payload = {"missing_fields": missing_fields}
    return SimpleNamespace(
        intent=intent,
        success=success,
        fallback=fallback_payload,
        result={"tool_results": {tool: {"success": True} for tool in (tools or [])}},
        agent_runtime={
            "tool_results": tools or [],
            "plan_actions": actions or [],
            "fallback_used": False,
            "trace_id": "trace-1",
        },
    )


def test_normalize_tool_list_maps_legacy_names_and_ignores_internal_steps():
    assert normalize_tool_list(["parse_task", "fetch_weather", "evaluate_risk"]) == ["evaluate_flight_risk"]


def test_evaluate_case_passes_when_expected_tool_is_called():
    case = {
        "id": "case-1",
        "category": "evaluate",
        "expected_intent": "evaluate",
        "expected_tools": ["evaluate_flight_risk"],
        "unexpected_tools": ["query_user_history"],
        "expected_fallback": False,
    }

    result = evaluate_case(case, _response(tools=["evaluate_flight_risk"], actions=["call_tool"]))

    assert result["passed"] is True
    assert result["checks"]["expected_tools_hit"] is True
    assert result["missing_tools"] == []


def test_evaluate_case_detects_missing_and_unexpected_tools():
    case = {
        "id": "case-1",
        "category": "evaluate",
        "expected_intent": "evaluate",
        "expected_tools": ["evaluate_flight_risk"],
        "unexpected_tools": ["query_user_history"],
        "expected_fallback": False,
    }

    result = evaluate_case(case, _response(tools=["query_user_history"], actions=["call_tool"]))

    assert result["passed"] is False
    assert result["missing_tools"] == ["evaluate_flight_risk"]
    assert result["unexpected_called"] == ["query_user_history"]


def test_evaluate_case_handles_clarification_by_plan_action():
    case = {
        "id": "case-1",
        "category": "clarification",
        "expected_intent": "evaluate",
        "expected_route": "clarification",
        "expected_tools": ["ask_clarification"],
        "unexpected_tools": ["evaluate_flight_risk"],
        "expected_missing_fields": ["location"],
        "expected_fallback": False,
    }

    result = evaluate_case(
        case,
        _response(
            intent="evaluate",
            tools=[],
            actions=["ask_clarification"],
            success=False,
            missing_fields=["location", "task_type"],
        ),
    )

    assert result["passed"] is True
    assert result["checks"]["clarification_pass"] is True


def test_summarize_results_computes_core_metrics():
    results = [
        {
            "passed": True,
            "category": "evaluate",
            "expected_tools": ["evaluate_flight_risk"],
            "missing_tools": [],
            "unexpected_tools": ["query_user_history"],
            "unexpected_called": [],
            "extra_tools": [],
            "checks": {
                "intent_pass": True,
                "expected_tools_hit": True,
                "exact_tool_match": True,
                "fallback_pass": True,
                "clarification_pass": None,
            },
        },
        {
            "passed": False,
            "category": "evaluate",
            "expected_tools": ["evaluate_flight_risk"],
            "missing_tools": ["evaluate_flight_risk"],
            "unexpected_tools": ["query_user_history"],
            "unexpected_called": ["query_user_history"],
            "extra_tools": ["query_user_history"],
            "checks": {
                "intent_pass": True,
                "expected_tools_hit": False,
                "exact_tool_match": False,
                "fallback_pass": True,
                "clarification_pass": None,
            },
        },
    ]

    summary = summarize_results(results)

    assert summary.total_cases == 2
    assert summary.pass_rate == 0.5
    assert summary.tool_selection_accuracy == 0.5
    assert summary.extra_tool_call_rate == 0.5
    assert summary.missing_tool_call_rate == 0.5
    assert summary.unexpected_tool_violation_rate == 0.5
