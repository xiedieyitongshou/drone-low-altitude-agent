from unittest.mock import patch

from app.agent import AgentLoopResult, ToolResult, initialize_state, mark_completed, record_tool_result
from app.schemas import OrchestratorResponse
from app.services.nl_parser import ParsedTaskRequest
from app.services.task_orchestrator import orchestrate_task_query


def _legacy_response() -> OrchestratorResponse:
    return OrchestratorResponse(
        session_id="session-1",
        user_id="user-1",
        intent="evaluate",
        target_endpoint="/cruise/evaluate",
        parser_source="rule",
        parsed={"location": "深圳"},
        message="legacy ok",
    )


def _parsed_request() -> ParsedTaskRequest:
    return ParsedTaskRequest(
        intent="evaluate",
        target_endpoint="/cruise/evaluate",
        parsed={
            "location": "深圳",
            "date": "2026-08-01",
            "start_time": "14:00",
            "end_time": "17:00",
            "task_type": "inspection",
        },
        warnings=[],
        parser_source="rule",
    )


def test_agent_runtime_default_mode_uses_legacy_workflow():
    with patch.dict("os.environ", {}, clear=True), patch(
        "app.services.task_orchestrator._orchestrate_task_query_legacy",
        return_value=_legacy_response(),
    ) as legacy_mock:
        response = orchestrate_task_query("评估深圳", session_id="session-1", user_id="user-1")

    assert response.message == "legacy ok"
    assert response.agent_runtime is None
    legacy_mock.assert_called_once_with("评估深圳", session_id="session-1", user_id="user-1")


def test_agent_runtime_unknown_mode_falls_back_to_legacy_workflow():
    with patch.dict("os.environ", {"AGENT_RUNTIME_MODE": "bad"}, clear=False), patch(
        "app.services.task_orchestrator._orchestrate_task_query_legacy",
        return_value=_legacy_response(),
    ) as legacy_mock:
        response = orchestrate_task_query("评估深圳", session_id="session-1", user_id="user-1")

    assert response.message == "legacy ok"
    assert response.agent_runtime is None
    legacy_mock.assert_called_once_with("评估深圳", session_id="session-1", user_id="user-1")


def test_agent_runtime_loop_mode_returns_compatible_response():
    state = initialize_state("评估深圳", user_id="user-1", session_id="session-1")
    state = record_tool_result(
        state,
        tool_name="evaluate_flight_risk",
        tool_result=ToolResult(success=True, tool_name="evaluate_flight_risk", data={"overall_decision": "caution"}),
    )
    state = mark_completed(state, message="done")
    loop_result = AgentLoopResult(
        success=True,
        final_state=state,
        message="agent loop completed",
        output={"tool_results": {"evaluate_flight_risk": {"data": {"overall_decision": "caution"}}}},
    )

    with patch.dict("os.environ", {"AGENT_RUNTIME_MODE": "loop"}, clear=False), patch(
        "app.services.task_orchestrator.get_or_create_user_profile",
        return_value=None,
    ), patch(
        "app.services.task_orchestrator.merge_profile_context",
        return_value={},
    ), patch(
        "app.services.task_orchestrator._parse_task_query",
        return_value=_parsed_request(),
    ), patch(
        "app.services.task_orchestrator.AgentLoop.run",
        return_value=loop_result,
    ), patch(
        "app.services.task_orchestrator._save_context",
    ), patch(
        "app.services.task_orchestrator.update_profile_from_parsed",
    ), patch(
        "app.services.task_orchestrator._with_conversation_record",
        side_effect=lambda **kwargs: kwargs["response"],
    ):
        response = orchestrate_task_query("评估深圳", session_id="session-1", user_id="user-1")

    assert response.success is True
    assert response.intent == "evaluate"
    assert response.target_endpoint == "/cruise/evaluate"
    assert response.result == {"tool_results": {"evaluate_flight_risk": {"data": {"overall_decision": "caution"}}}}
    assert response.agent_runtime["mode"] == "loop"
    assert response.agent_runtime["status"] == "completed"
    assert response.agent_runtime["tool_results"] == ["evaluate_flight_risk"]


def test_agent_runtime_loop_mode_returns_legacy_response_when_loop_fallback_result_exists():
    state = initialize_state("评估深圳", user_id="user-1", session_id="session-1")
    loop_result = AgentLoopResult(
        success=False,
        final_state=state,
        message="fallback",
        fallback_used=True,
        fallback_result=_legacy_response(),
    )

    with patch.dict("os.environ", {"AGENT_RUNTIME_MODE": "loop"}, clear=False), patch(
        "app.services.task_orchestrator.get_or_create_user_profile",
        return_value=None,
    ), patch(
        "app.services.task_orchestrator.merge_profile_context",
        return_value={},
    ), patch(
        "app.services.task_orchestrator._parse_task_query",
        return_value=_parsed_request(),
    ), patch(
        "app.services.task_orchestrator.AgentLoop.run",
        return_value=loop_result,
    ):
        response = orchestrate_task_query("评估深圳", session_id="session-1", user_id="user-1")

    assert response.message == "legacy ok"
    assert response.agent_runtime["fallback_used"] is True
    assert response.agent_runtime["mode"] == "loop"
