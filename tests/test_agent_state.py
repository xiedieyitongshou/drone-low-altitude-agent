from app.agent import (
    AgentStatus,
    ToolResult,
    initialize_state,
    mark_completed,
    mark_failed,
    mark_needs_clarification,
    mark_parsed,
    mark_tool_running,
    merge_user_input,
    record_tool_result,
)


def test_initialize_state_creates_ids_and_first_step():
    state = initialize_state("帮我看深圳明天下午适不适合飞", user_id="user-1", session_id="session-1")

    assert state.status == AgentStatus.INITIALIZED
    assert state.user_id == "user-1"
    assert state.session_id == "session-1"
    assert state.trace_id
    assert state.run_id
    assert state.round_index == 1
    assert state.steps[0].event == "initialize"


def test_mark_parsed_moves_to_ready_when_no_missing_fields():
    state = initialize_state("帮我评估深圳")
    state = mark_parsed(
        state,
        intent="evaluate",
        parsed={
            "location": "深圳",
            "date": "2026-08-01",
            "task_type": "inspection",
        },
    )

    assert state.status == AgentStatus.READY_TO_PLAN
    assert state.current_intent == "evaluate"
    assert state.task_draft["location"] == "深圳"
    assert state.confirmed_fields == {"location", "date", "task_type"}
    assert state.missing_fields == []
    assert state.steps[-1].state_delta["next_status"] == "ready_to_plan"


def test_mark_parsed_moves_to_clarification_when_fields_missing():
    state = initialize_state("明天适合飞吗")
    state = mark_parsed(
        state,
        intent="evaluate",
        parsed={"date": "2026-08-01"},
        missing_fields=["location", "task_type"],
    )

    assert state.status == AgentStatus.NEEDS_CLARIFICATION
    assert state.missing_fields == ["location", "task_type"]
    assert state.task_draft["date"] == "2026-08-01"


def test_merge_user_input_updates_draft_and_removes_missing_fields():
    state = initialize_state("明天适合飞吗")
    state = mark_needs_clarification(state, ["location", "task_type"])
    state = merge_user_input(state, {"location": "深圳湾", "task_type": "inspection"})

    assert state.task_draft["location"] == "深圳湾"
    assert state.task_draft["task_type"] == "inspection"
    assert state.confirmed_fields == {"location", "task_type"}
    assert state.missing_fields == []
    assert state.steps[-1].event == "merge_user_input"
    assert state.steps[-1].state_delta["changed_fields"] == ["location", "task_type"]


def test_record_successful_tool_result_updates_state():
    state = initialize_state("帮我评估深圳")
    state = mark_tool_running(state, tool_name="evaluate_flight_risk", tool_input={"location": "深圳"})
    result = ToolResult(success=True, tool_name="evaluate_flight_risk", data={"overall_decision": "caution"})
    state = record_tool_result(state, tool_name="evaluate_flight_risk", tool_result=result)

    assert state.status == AgentStatus.TOOL_COMPLETED
    assert state.tool_results["evaluate_flight_risk"].data == {"overall_decision": "caution"}
    assert state.errors == []
    assert state.steps[-1].state_delta["success"] is True


def test_record_failed_tool_result_updates_errors():
    state = initialize_state("帮我评估深圳")
    result = ToolResult(
        success=False,
        tool_name="evaluate_flight_risk",
        error_code="WEATHER_TIMEOUT",
        message="weather service timeout",
    )
    state = record_tool_result(state, tool_name="evaluate_flight_risk", tool_result=result)

    assert state.status == AgentStatus.FAILED
    assert state.errors == [
        {
            "tool_name": "evaluate_flight_risk",
            "error_code": "WEATHER_TIMEOUT",
            "message": "weather service timeout",
        }
    ]
    assert state.steps[-1].status == AgentStatus.FAILED


def test_mark_completed_and_failed_are_explicit_terminal_transitions():
    state = initialize_state("帮我评估深圳")
    completed = mark_completed(state, message="done")
    failed = mark_failed(state, error_code="STATE_ERROR", message="invalid state")

    assert completed.status == AgentStatus.COMPLETED
    assert completed.steps[-1].event == "complete"
    assert failed.status == AgentStatus.FAILED
    assert failed.errors[-1]["error_code"] == "STATE_ERROR"
