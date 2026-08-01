from app.agent import (
    AgentLoop,
    AgentStatus,
    ToolExecutionContext,
    ToolExecutor,
    ToolRegistry,
    ToolSpec,
    TraceEventType,
    initialize_state,
    mark_parsed,
    mark_tool_running,
)


def _build_registry(handler):
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="evaluate_flight_risk",
            description="Fake risk evaluation.",
            side_effect="compute_only",
            risk_level="high",
        ),
        handler,
    )
    return registry


def test_tool_executor_records_tool_call_and_result_events():
    events = []
    registry = _build_registry(lambda payload, context: {"location": payload["location"]})
    executor = ToolExecutor(tool_registry=registry, trace_recorder=events.append)
    state = initialize_state("评估深圳", user_id="user-1", session_id="session-1")
    state = mark_tool_running(state, tool_name="evaluate_flight_risk", tool_input={"location": "深圳"})

    result = executor.execute(
        tool_name="evaluate_flight_risk",
        tool_input={"location": "深圳"},
        state=state,
        context=ToolExecutionContext(user_id="user-1", tenant_id="tenant-1", role="user"),
    )

    assert result.success is True
    assert [event.event_type for event in events] == [TraceEventType.TOOL_CALL, TraceEventType.TOOL_RESULT]
    assert events[0].trace_id == state.trace_id
    assert events[0].run_id == state.run_id
    assert events[0].user_id == "user-1"
    assert events[0].session_id == "session-1"
    assert events[0].tool_name == "evaluate_flight_risk"
    assert events[0].input_summary == {"location": "深圳"}
    assert events[0].metadata["side_effect"] == "compute_only"
    assert events[1].status_before == AgentStatus.TOOL_RUNNING.value
    assert events[1].status_after == AgentStatus.TOOL_COMPLETED.value
    assert events[1].latency_ms >= 0
    assert events[1].output_summary["success"] is True
    assert events[1].output_summary["data"] == {"location": "深圳"}


def test_tool_executor_records_error_event_when_tool_fails():
    events = []

    def broken_handler(payload, context):
        raise RuntimeError("weather failed")

    registry = _build_registry(broken_handler)
    executor = ToolExecutor(tool_registry=registry, trace_recorder=events.append)
    state = initialize_state("评估深圳", user_id="user-1")
    state = mark_tool_running(state, tool_name="evaluate_flight_risk", tool_input={"location": "深圳"})

    result = executor.execute(
        tool_name="evaluate_flight_risk",
        tool_input={"location": "深圳"},
        state=state,
        context=ToolExecutionContext(user_id="user-1"),
    )

    assert result.success is False
    assert [event.event_type for event in events] == [
        TraceEventType.TOOL_CALL,
        TraceEventType.TOOL_RESULT,
        TraceEventType.ERROR,
    ]
    assert events[1].error_code == "RuntimeError"
    assert events[1].status_after == AgentStatus.FAILED.value
    assert events[1].metadata["failure_type"] == "internal_error"
    assert events[1].metadata["recovery_action"] == "fallback_legacy"
    assert events[1].metadata["retryable"] is False
    assert events[2].error_code == "RuntimeError"
    assert events[2].message == "工具执行出现内部错误，已尝试使用兼容链路处理。"
    assert events[2].metadata["failure_type"] == "internal_error"


def test_tool_executor_ignores_trace_recorder_failure():
    def broken_recorder(event):
        raise RuntimeError("trace db unavailable")

    registry = _build_registry(lambda payload, context: {"ok": True})
    executor = ToolExecutor(tool_registry=registry, trace_recorder=broken_recorder)
    state = initialize_state("评估深圳", user_id="user-1")
    state = mark_tool_running(state, tool_name="evaluate_flight_risk")

    result = executor.execute(
        tool_name="evaluate_flight_risk",
        tool_input={"location": "深圳"},
        state=state,
        context=ToolExecutionContext(user_id="user-1"),
    )

    assert result.success is True
    assert result.data == {"ok": True}


def test_agent_loop_uses_tool_executor_for_trace_records():
    events = []
    registry = _build_registry(lambda payload, context: {"location": payload["location"]})
    executor = ToolExecutor(tool_registry=registry, trace_recorder=events.append)
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

    result = AgentLoop(tool_registry=registry, tool_executor=executor).run(state)

    assert result.success is True
    assert [event.event_type for event in events] == [TraceEventType.TOOL_CALL, TraceEventType.TOOL_RESULT]
    assert events[0].tool_name == "evaluate_flight_risk"
    assert result.final_state.status == AgentStatus.COMPLETED
