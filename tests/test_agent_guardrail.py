from app.agent import (
    AgentLoop,
    AgentStatus,
    GuardrailAction,
    GuardrailCheckpoint,
    ToolExecutionContext,
    ToolExecutor,
    ToolRegistry,
    ToolSpec,
    check_input_guardrail,
    check_output_guardrail,
    check_tool_guardrail,
    guardrail_metadata,
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


def test_tool_guardrail_rejects_role_not_allowed():
    state = initialize_state("管理员审计", user_id="user-1")
    tool_spec = ToolSpec(
        name="admin_audit",
        description="Admin audit tool.",
        side_effect="read_only",
        risk_level="medium",
        allowed_roles=["admin"],
        user_scope="admin",
    )

    result = check_tool_guardrail(
        tool_spec=tool_spec,
        tool_input={},
        state=state,
        context=ToolExecutionContext(user_id="user-1", role="user"),
    )

    assert result.allowed is False
    assert result.action == GuardrailAction.BLOCK
    assert result.error_code == "TOOL_PERMISSION_DENIED"
    assert result.metadata["violation_type"] == "role_not_allowed"


def test_tool_guardrail_rejects_payload_user_id_mismatch():
    state = initialize_state("查我的历史", user_id="user-1")
    tool_spec = ToolSpec(
        name="query_user_history",
        description="Query current user history.",
        side_effect="read_only",
        risk_level="low",
    )

    result = check_tool_guardrail(
        tool_spec=tool_spec,
        tool_input={"user_id": "user-2", "keyword": "深圳"},
        state=state,
        context=ToolExecutionContext(user_id="user-1", role="user"),
    )

    assert result.allowed is False
    assert result.action == GuardrailAction.BLOCK
    assert result.error_code == "TOOL_USER_SCOPE_VIOLATION"
    assert result.metadata["violation_type"] == "payload_user_id_mismatch"
    assert result.metadata["payload_user_id"] == "user-2"


def test_guardrail_metadata_contains_user_readable_explanation():
    state = initialize_state("查我的历史", user_id="user-1")
    tool_spec = ToolSpec(
        name="query_user_history",
        description="Query current user history.",
        side_effect="read_only",
        risk_level="low",
    )
    result = check_tool_guardrail(
        tool_spec=tool_spec,
        tool_input={"user_id": "user-2"},
        state=state,
        context=ToolExecutionContext(user_id="user-1", role="user"),
    )

    metadata = guardrail_metadata(result)

    assert metadata["guardrail_checkpoint"] == "tool"
    assert metadata["guardrail_action"] == "block"
    assert metadata["violation_type"] == "payload_user_id_mismatch"
    assert metadata["guardrail_user_message"] == "请求中的用户身份与当前登录用户不一致，系统已拒绝越权访问。"
    assert metadata["guardrail_explanation"]["tool_name"] == "query_user_history"
    assert metadata["guardrail_explanation"]["violation_type"] == "payload_user_id_mismatch"


def test_tool_executor_blocks_user_scope_violation_before_handler_runs():
    registry = ToolRegistry()
    handler_calls = []
    registry.register(
        ToolSpec(
            name="query_user_history",
            description="Query current user history.",
            side_effect="read_only",
            risk_level="low",
        ),
        lambda payload, context: handler_calls.append(payload) or {"items": []},
    )
    state = initialize_state("查我的历史", user_id="user-1")
    executor = ToolExecutor(tool_registry=registry, trace_recorder=None)

    result = executor.execute(
        tool_name="query_user_history",
        tool_input={"user_id": "user-2", "keyword": "深圳"},
        state=state,
        context=ToolExecutionContext(user_id="user-1", role="user"),
    )

    assert result.success is False
    assert result.error_code == "TOOL_USER_SCOPE_VIOLATION"
    assert result.metadata["guardrail_checkpoint"] == "tool"
    assert result.metadata["guardrail_explanation"]["user_message"] == "请求中的用户身份与当前登录用户不一致，系统已拒绝越权访问。"
    assert handler_calls == []


def test_tool_executor_records_guardrail_explanation_to_trace():
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="query_user_history",
            description="Query current user history.",
            side_effect="read_only",
            risk_level="low",
        ),
        lambda payload, context: {"items": []},
    )
    trace_events = []
    state = initialize_state("查我的历史", user_id="user-1")
    executor = ToolExecutor(tool_registry=registry, trace_recorder=trace_events.append)

    executor.execute(
        tool_name="query_user_history",
        tool_input={"user_id": "user-2"},
        state=state,
        context=ToolExecutionContext(user_id="user-1", role="user"),
    )

    error_events = [event for event in trace_events if event.error_code == "TOOL_USER_SCOPE_VIOLATION"]
    assert error_events
    assert error_events[0].metadata["source"] == "tool_guardrail"
    assert error_events[0].metadata["guardrail_explanation"]["checkpoint"] == "tool"


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
    assert result.output["guardrail"]["checkpoint"] == "input"
    assert result.output["guardrail"]["action"] == "block"
    assert result.output["guardrail"]["user_message"] == "当前输入涉及绕过监管或危险操作，系统已拒绝继续执行。"
    assert result.plans == []
