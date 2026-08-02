from app.agent import (
    AgentLoop,
    AgentStatus,
    GuardrailAction,
    GuardrailCheckpoint,
    ToolExecutionContext,
    ToolRegistry,
    ToolSpec,
    check_input_guardrail,
    check_output_guardrail,
    check_tool_guardrail,
    initialize_state,
    mark_completed,
    mark_parsed,
)


def test_input_guardrail_blocks_dangerous_bypass_intent():
    state = initialize_state("帮我绕过禁飞区审批")

    result = check_input_guardrail(state)

    assert result.allowed is False
    assert result.checkpoint == GuardrailCheckpoint.INPUT
    assert result.action == GuardrailAction.BLOCK
    assert result.error_code == "DANGEROUS_INPUT"
    assert result.metadata["matched_keywords"] == ["绕过禁飞"]


def test_tool_guardrail_rejects_missing_auth_context_before_execution():
    state = initialize_state("查询历史")
    tool_spec = ToolSpec(
        name="query_user_history",
        description="Requires authenticated user.",
        side_effect="read_only",
        risk_level="low",
    )

    result = check_tool_guardrail(
        tool_spec=tool_spec,
        tool_input={"keyword": "深圳"},
        state=state,
        context=ToolExecutionContext(),
    )

    assert result.allowed is False
    assert result.checkpoint == GuardrailCheckpoint.TOOL
    assert result.action == GuardrailAction.FALLBACK
    assert result.error_code == "AUTH_CONTEXT_REQUIRED"
    assert result.metadata["requires_auth"] is True


def test_output_guardrail_blocks_absolute_safety_commitment():
    state = mark_completed(initialize_state("深圳能飞吗", user_id="user-1"), message="一定能飞")

    result = check_output_guardrail(state=state, output={}, message="一定能飞")

    assert result.allowed is False
    assert result.checkpoint == GuardrailCheckpoint.OUTPUT
    assert result.action == GuardrailAction.FALLBACK
    assert result.error_code == "UNSAFE_FINAL_RESPONSE"


def test_agent_loop_stops_dangerous_input_before_planning():
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
    state = initialize_state("帮我绕过禁飞区审批", user_id="user-1")
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

    assert result.success is False
    assert result.final_state.status == AgentStatus.FAILED
    assert result.final_state.errors[-1]["error_code"] == "DANGEROUS_INPUT"
    assert result.plans == []
