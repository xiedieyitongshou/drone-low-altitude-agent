from app.agent import (
    AgentLoop,
    AgentPlanAction,
    AgentStatus,
    ToolExecutionContext,
    ToolRegistry,
    ToolSpec,
    initialize_state,
    mark_parsed,
)


def test_agent_loop_calls_planned_tool_and_completes():
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="evaluate_flight_risk",
            description="Fake risk evaluation.",
            side_effect="compute_only",
            risk_level="high",
        ),
        lambda payload, context: {"overall_decision": "caution", "location": payload["location"]},
    )
    state = initialize_state("评估深圳", user_id="user-1")
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

    result = AgentLoop(tool_registry=registry).run(state)

    assert result.success is True
    assert result.final_state.status == AgentStatus.COMPLETED
    assert result.output["tool_results"]["evaluate_flight_risk"]["data"] == {
        "overall_decision": "caution",
        "location": "深圳",
    }
    assert [plan.action for plan in result.plans] == [
        AgentPlanAction.CALL_TOOL,
        AgentPlanAction.RESPOND_DIRECTLY,
    ]
    assert result.final_state.steps[-1].event == "complete"


def test_agent_loop_returns_clarification_when_fields_missing():
    state = initialize_state("明天下午适合飞吗", user_id="user-1")
    state = mark_parsed(
        state,
        intent="evaluate",
        parsed={"date": "2026-08-01", "task_type": "inspection"},
        missing_fields=["location", "start_time", "end_time"],
    )

    result = AgentLoop(tool_registry=ToolRegistry()).run(state)

    assert result.success is True
    assert result.requires_clarification is True
    assert result.final_state.status == AgentStatus.NEEDS_CLARIFICATION
    assert result.final_state.missing_fields == ["location", "start_time", "end_time"]
    assert result.last_plan.action == AgentPlanAction.ASK_CLARIFICATION


def test_agent_loop_uses_fallback_when_tool_fails():
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="evaluate_flight_risk",
            description="Broken risk evaluation.",
            side_effect="compute_only",
            risk_level="high",
        ),
        lambda payload, context: (_ for _ in ()).throw(RuntimeError("weather failed")),
    )
    fallback_calls = []

    def fallback_handler(state, plan):
        fallback_calls.append((state.status, plan.tool_name if plan else None))
        return {"source": "legacy_workflow"}

    state = initialize_state("评估深圳", user_id="user-1")
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

    result = AgentLoop(tool_registry=registry, fallback_handler=fallback_handler).run(state)

    assert result.success is False
    assert result.fallback_used is True
    assert result.fallback_result == {"source": "legacy_workflow"}
    assert fallback_calls == [(AgentStatus.FAILED, "evaluate_flight_risk")]
    assert result.final_state.errors[-1]["error_code"] == "RuntimeError"


def test_agent_loop_fallback_when_tool_requires_auth_context():
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="query_user_history",
            description="Requires authenticated user.",
            side_effect="read_only",
            risk_level="low",
        ),
        lambda payload, context: {"items": []},
    )
    state = initialize_state("查询历史")
    state = mark_parsed(state, intent="history", parsed={"keyword": "深圳"})

    result = AgentLoop(tool_registry=registry).run(state, context=ToolExecutionContext())

    assert result.success is False
    assert result.final_state.status == AgentStatus.FAILED
    assert result.final_state.errors[-1]["error_code"] == "AUTH_CONTEXT_REQUIRED"
    assert result.message == "缺少登录上下文，已尝试使用兼容链路处理。"
    assert result.output["recovery_action"] == "fallback_legacy"
    assert result.output["fallback_used"] is False


def test_agent_loop_denies_permission_error_without_legacy_fallback():
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="query_user_history",
            description="Requires admin user.",
            side_effect="read_only",
            risk_level="low",
            requires_admin=True,
        ),
        lambda payload, context: {"items": []},
    )
    fallback_calls = []
    state = initialize_state("查询历史", user_id="user-1")
    state = mark_parsed(state, intent="history", parsed={"keyword": "深圳"})

    result = AgentLoop(tool_registry=registry, fallback_handler=lambda state, plan: fallback_calls.append(plan)).run(
        state,
        context=ToolExecutionContext(user_id="user-1", role="user"),
    )

    assert result.success is False
    assert result.fallback_used is False
    assert fallback_calls == []
    assert result.message == "当前用户没有权限执行该工具。"
    assert result.final_state.errors[-1]["error_code"] == "ADMIN_CONTEXT_REQUIRED"
    assert result.output["recovery_action"] == "deny"
    assert result.output["fallback_used"] is False


def test_agent_loop_returns_user_readable_direct_response_for_not_found():
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="query_user_history",
            description="History tool not found result.",
            side_effect="read_only",
            risk_level="low",
            requires_auth=False,
        ),
        lambda payload, context: (_ for _ in ()).throw(KeyError("not found")),
    )
    state = initialize_state("查询历史")
    state = mark_parsed(state, intent="history", parsed={"keyword": "不存在"})

    result = AgentLoop(tool_registry=registry).run(state)

    assert result.success is True
    assert "历史记录" in result.message
    assert result.output["recovery_action"] == "direct_response"
    assert result.output["failure_type"] == "not_found"


def test_agent_loop_protects_against_infinite_loop():
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="evaluate_flight_risk",
            description="Fake risk evaluation.",
            side_effect="compute_only",
            risk_level="high",
        ),
        lambda payload, context: {"ok": True},
    )
    state = initialize_state("评估深圳", user_id="user-1")
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

    result = AgentLoop(tool_registry=registry, max_iterations=1).run(state)

    assert result.success is False
    assert result.final_state.status == AgentStatus.FAILED
    assert result.final_state.errors[-1]["error_code"] == "AGENT_LOOP_MAX_ITERATIONS"
