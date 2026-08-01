from app.agent import (
    ToolFailureType,
    ToolRecoveryAction,
    ToolFailurePolicy,
    build_agent_fallback_output,
    build_clarification_message,
    build_empty_result_message,
    build_tool_failure_message,
    initialize_state,
)


def test_build_clarification_message_uses_chinese_field_names():
    assert build_clarification_message(["location", "start_time", "end_time"]) == (
        "还需要补充以下信息后才能继续：任务地点、开始时间、结束时间。"
    )


def test_build_empty_result_message_by_tool_name():
    assert "知识库没有召回" in build_empty_result_message("retrieve_rag_advice")
    assert "历史记录" in build_empty_result_message("query_user_history")
    assert "推荐窗口" in build_empty_result_message("recommend_flight_windows")


def test_build_tool_failure_message_handles_permission_and_empty_result():
    denied = ToolFailurePolicy(
        failure_type=ToolFailureType.PERMISSION_DENIED,
        recovery_action=ToolRecoveryAction.DENY,
        retryable=False,
        user_message="当前用户没有权限执行该工具。",
    )
    not_found = ToolFailurePolicy(
        failure_type=ToolFailureType.NOT_FOUND,
        recovery_action=ToolRecoveryAction.DIRECT_RESPONSE,
        retryable=False,
        user_message="未找到匹配结果，请调整查询条件。",
    )

    assert build_tool_failure_message(policy=denied) == "当前用户没有权限执行该工具。"
    assert "知识库没有召回" in build_tool_failure_message(policy=not_found, tool_name="retrieve_rag_advice")


def test_build_agent_fallback_output_contains_trace_and_policy():
    state = initialize_state("查一下政策", user_id="user-1")
    policy = ToolFailurePolicy(
        failure_type=ToolFailureType.TIMEOUT,
        recovery_action=ToolRecoveryAction.RETRY,
        retryable=True,
        user_message="工具调用超时，可重试一次；仍失败时进入兼容兜底。",
    )

    output = build_agent_fallback_output(
        state=state,
        message=policy.user_message,
        policy=policy,
        tool_name="fetch_weather_context",
        fallback_used=True,
    )

    assert output["message"] == policy.user_message
    assert output["trace_id"] == state.trace_id
    assert output["run_id"] == state.run_id
    assert output["tool_name"] == "fetch_weather_context"
    assert output["failure_type"] == "timeout"
    assert output["recovery_action"] == "retry"
    assert output["retryable"] is True
    assert output["fallback_used"] is True
