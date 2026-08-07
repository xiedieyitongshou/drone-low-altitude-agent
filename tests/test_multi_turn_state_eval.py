from scripts.multi_turn_state_eval import evaluate_turn_checks, summarize_results


def test_evaluate_turn_checks_passes_inheritance_and_override():
    checks = evaluate_turn_checks(
        turn={
            "expected_intent": "evaluate",
            "expected_tool": "evaluate_flight_risk",
            "expected_state": {
                "location": "广州",
                "date": "2026-08-08",
                "start_time": "14:00",
                "end_time": "17:00",
            },
            "expected_tool_input": {
                "location": "广州",
                "date": "2026-08-08",
            },
            "expected_inherited_fields": ["date", "start_time", "end_time"],
            "expected_modified_fields": ["location"],
            "expected_invalidated_tools": ["evaluate_flight_risk"],
        },
        actual_intent="evaluate",
        actual_action="call_tool",
        actual_tool="evaluate_flight_risk",
        actual_state={
            "location": "广州",
            "date": "2026-08-08",
            "start_time": "14:00",
            "end_time": "17:00",
        },
        actual_tool_input={
            "location": "广州",
            "date": "2026-08-08",
        },
        previous_state={
            "location": "深圳",
            "date": "2026-08-08",
            "start_time": "14:00",
            "end_time": "17:00",
        },
        modified_fields=["location"],
        invalidated_tools=["evaluate_flight_risk", "query_knowledge_snippets"],
        missing_fields=[],
    )

    assert checks["passed"] is True
    assert checks["inheritance_pass"] is True
    assert checks["override_pass"] is True


def test_evaluate_turn_checks_detects_context_pollution():
    checks = evaluate_turn_checks(
        turn={
            "expected_intent": "knowledge",
            "expected_tool": "query_knowledge_snippets",
            "expected_state": {"city": "广州", "task_type": "inspection"},
            "expected_absent_tool_input_fields": ["date", "start_time", "end_time"],
        },
        actual_intent="knowledge",
        actual_action="call_tool",
        actual_tool="query_knowledge_snippets",
        actual_state={"city": "广州", "task_type": "inspection"},
        actual_tool_input={
            "city": "广州",
            "task_type": "inspection",
            "date": "2026-08-08",
        },
        previous_state={},
        modified_fields=[],
        invalidated_tools=[],
        missing_fields=[],
    )

    assert checks["passed"] is False
    assert checks["no_context_pollution"] is False


def test_summarize_results_computes_state_metrics():
    results = [
        {
            "passed": True,
            "category": "field_override",
            "expected_modified_fields": ["location"],
            "expected_invalidated_tools": ["evaluate_flight_risk"],
            "checks": {
                "intent_pass": True,
                "tool_pass": True,
                "state_matches": {"location": True, "date": True},
                "tool_input_matches": {"location": True},
                "inherited_matches": {"date": True},
                "override_matches": {"location": True},
                "modified_fields_pass": True,
                "invalidated_tools_pass": True,
                "clarification_continuation_pass": None,
                "absent_tool_input_matches": {},
                "no_context_pollution": True,
                "session_isolation_pass": None,
            },
        },
        {
            "passed": False,
            "category": "context_pollution",
            "expected_modified_fields": [],
            "expected_invalidated_tools": [],
            "checks": {
                "intent_pass": True,
                "tool_pass": True,
                "state_matches": {"city": True},
                "tool_input_matches": {"city": True},
                "inherited_matches": {},
                "override_matches": {},
                "modified_fields_pass": True,
                "invalidated_tools_pass": True,
                "clarification_continuation_pass": None,
                "absent_tool_input_matches": {"date": False},
                "no_context_pollution": False,
                "session_isolation_pass": None,
            },
        },
    ]

    summary = summarize_results([{"id": "case-1"}], results)

    assert summary.total_turns == 2
    assert summary.pass_rate == 0.5
    assert summary.state_match_accuracy == 1.0
    assert summary.context_pollution_rate == 1.0
