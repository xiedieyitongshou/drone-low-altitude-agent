from app.agent import (
    AgentPlanAction,
    AgentStatus,
    ToolResult,
    initialize_state,
    mark_failed,
    mark_parsed,
    mark_tool_running,
    plan_next_step,
    record_tool_result,
)


def test_plan_asks_clarification_when_required_fields_missing():
    state = initialize_state("明天下午适合飞吗")
    state = mark_parsed(
        state,
        intent="evaluate",
        parsed={"date": "2026-08-01", "task_type": "inspection"},
        missing_fields=["location", "start_time", "end_time"],
    )

    plan = plan_next_step(state)

    assert plan.action == AgentPlanAction.ASK_CLARIFICATION
    assert plan.missing_fields == ["location", "start_time", "end_time"]
    assert plan.tool_name is None


def test_plan_derives_missing_fields_from_intent_requirements():
    state = initialize_state("评估深圳")
    state = mark_parsed(
        state,
        intent="evaluate",
        parsed={"location": "深圳", "date": "2026-08-01"},
    )

    plan = plan_next_step(state)

    assert plan.action == AgentPlanAction.ASK_CLARIFICATION
    assert plan.missing_fields == ["start_time", "end_time", "task_type"]


def test_plan_maps_evaluate_intent_to_risk_tool():
    state = initialize_state("评估深圳明天下午")
    state = mark_parsed(
        state,
        intent="evaluate",
        parsed={
            "location": "深圳",
            "date": "2026-08-01",
            "start_time": "14:00",
            "end_time": "17:00",
            "task_type": "inspection",
            "purpose": "巡检",
            "unused": "ignored",
        },
    )

    plan = plan_next_step(state)

    assert plan.action == AgentPlanAction.CALL_TOOL
    assert plan.tool_name == "evaluate_flight_risk"
    assert plan.tool_input == {
        "location": "深圳",
        "date": "2026-08-01",
        "start_time": "14:00",
        "end_time": "17:00",
        "task_type": "inspection",
        "purpose": "巡检",
    }
    assert plan.metadata["side_effect"] == "compute_only"
    assert plan.metadata["risk_level"] == "high"


def test_plan_maps_recommend_intent_to_recommendation_tool():
    state = initialize_state("推荐深圳飞行窗口")
    state = mark_parsed(
        state,
        intent="recommend",
        parsed={
            "location": "深圳",
            "date": "2026-08-01",
            "task_type": "inspection",
            "scan_hours": 48,
            "min_window_hours": 3,
        },
    )

    plan = plan_next_step(state)

    assert plan.action == AgentPlanAction.CALL_TOOL
    assert plan.tool_name == "recommend_flight_windows"
    assert plan.tool_input["scan_hours"] == 48
    assert plan.tool_input["min_window_hours"] == 3


def test_plan_maps_compare_intent_to_comparison_tool():
    state = initialize_state("深圳湾和黄鹤楼哪个更适合飞")
    state = mark_parsed(
        state,
        intent="compare",
        parsed={
            "locations": ["深圳湾", "黄鹤楼"],
            "date": "2026-08-01",
            "start_time": "14:00",
            "end_time": "17:00",
            "task_type": "inspection",
            "top_k": 2,
        },
    )

    plan = plan_next_step(state)

    assert plan.action == AgentPlanAction.CALL_TOOL
    assert plan.tool_name == "compare_flight_locations"
    assert plan.tool_input["locations"] == ["深圳湾", "黄鹤楼"]
    assert plan.tool_input["top_k"] == 2


def test_plan_maps_knowledge_intent_to_rag_tool_with_metadata_context():
    state = initialize_state("深圳无人机政策有什么要注意")
    state = mark_parsed(
        state,
        intent="knowledge",
        parsed={
            "task_type": "inspection",
            "risk_reasons": ["强风"],
            "province": "广东",
            "city": "深圳",
            "top_k": 3,
        },
    )

    plan = plan_next_step(state)

    assert plan.action == AgentPlanAction.CALL_TOOL
    assert plan.tool_name == "query_knowledge_snippets"
    assert plan.tool_input == {
        "task_type": "inspection",
        "risk_reasons": ["强风"],
        "province": "广东",
        "city": "深圳",
        "top_k": 3,
    }
    assert plan.metadata["side_effect"] == "read_only"
    assert plan.metadata["route_kind"] == "knowledge_query"
    assert plan.metadata["target_endpoint"] == "/knowledge/advice/retrieve"


def test_plan_maps_explain_intent_to_rule_explanation_tool():
    state = initialize_state("为什么判高风险")
    state = mark_parsed(
        state,
        intent="explain",
        parsed={
            "query": "为什么判高风险",
            "task_type": "inspection",
            "overall_decision": "禁飞",
            "risk_reasons": ["风速偏高"],
        },
    )

    plan = plan_next_step(state)

    assert plan.action == AgentPlanAction.CALL_TOOL
    assert plan.tool_name == "explain_risk_rules"
    assert plan.tool_input["overall_decision"] == "禁飞"
    assert plan.tool_input["risk_reasons"] == ["风速偏高"]
    assert plan.metadata["route_kind"] == "explanation_query"


def test_plan_maps_history_intent_to_history_tool():
    state = initialize_state("查一下我上次深圳任务")
    state = mark_parsed(
        state,
        intent="history",
        parsed={"keyword": "深圳", "page": 1, "page_size": 10},
    )

    plan = plan_next_step(state)

    assert plan.action == AgentPlanAction.CALL_TOOL
    assert plan.tool_name == "query_user_history"
    assert plan.tool_input["keyword"] == "深圳"
    assert plan.metadata["route_kind"] == "history_query"


def test_plan_responds_directly_when_tool_result_already_exists():
    state = initialize_state("评估深圳")
    state = mark_parsed(
        state,
        intent="evaluate",
        parsed={
            "location": "深圳",
            "date": "2026-08-01",
            "start_time": "14:00",
            "end_time": "17:00",
            "task_type": "inspection",
        },
    )
    state = record_tool_result(
        state,
        tool_name="evaluate_flight_risk",
        tool_result=ToolResult(success=True, tool_name="evaluate_flight_risk", data={"ok": True}),
    )

    plan = plan_next_step(state)

    assert plan.action == AgentPlanAction.RESPOND_DIRECTLY
    assert plan.metadata["tool_results"] == ["evaluate_flight_risk"]


def test_plan_fallback_for_failed_or_running_state():
    failed = mark_failed(initialize_state("评估深圳"), error_code="STATE_ERROR", message="bad state")
    running = mark_tool_running(initialize_state("评估深圳"), tool_name="evaluate_flight_risk")

    failed_plan = plan_next_step(failed)
    running_plan = plan_next_step(running)

    assert failed_plan.action == AgentPlanAction.FALLBACK
    assert failed_plan.metadata["errors"][0]["error_code"] == "STATE_ERROR"
    assert running.status == AgentStatus.TOOL_RUNNING
    assert running_plan.action == AgentPlanAction.FALLBACK


def test_plan_fallback_for_unsupported_intent():
    state = initialize_state("帮我订机票")
    state = mark_parsed(state, intent="book_flight", parsed={})

    plan = plan_next_step(state)

    assert plan.action == AgentPlanAction.FALLBACK
    assert "unsupported intent" in plan.reason
