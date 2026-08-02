from unittest.mock import patch

from app.agent import (
    AgentLoopResult,
    AgentPlanAction,
    ToolResult,
    build_agent_fallback_output,
    build_clarification_message,
    mark_completed,
    mark_needs_clarification,
    plan_next_step,
    record_tool_result,
)
from app.services.profile_memory import ProfileMemory
from app.services.session_memory import TTLSessionMemoryStore
from app.services.task_orchestrator import orchestrate_task_query


def _run_with_planner_only(self, state, context):
    plan = plan_next_step(state)
    if plan.action == AgentPlanAction.ASK_CLARIFICATION:
        message = build_clarification_message(plan.missing_fields)
        clarified = mark_needs_clarification(state, plan.missing_fields, message=message)
        return AgentLoopResult(
            success=True,
            final_state=clarified,
            message=message,
            output=build_agent_fallback_output(state=clarified, message=message),
            requires_clarification=True,
            last_plan=plan,
            plans=[plan],
        )

    if plan.action == AgentPlanAction.CALL_TOOL:
        tool_result = ToolResult(
            success=True,
            tool_name=str(plan.tool_name),
            data={
                "tool_name": plan.tool_name,
                "tool_input": plan.tool_input,
                "metadata": plan.metadata,
            },
        )
        completed = record_tool_result(state, tool_name=str(plan.tool_name), tool_result=tool_result)
        completed = mark_completed(completed, message="done")
        return AgentLoopResult(
            success=True,
            final_state=completed,
            message="done",
            output={
                "tool_results": {
                    str(plan.tool_name): tool_result.model_dump(mode="json"),
                }
            },
            last_plan=plan,
            plans=[plan],
        )

    completed = mark_completed(state, message=plan.reason)
    return AgentLoopResult(success=True, final_state=completed, message=plan.reason, output={}, last_plan=plan, plans=[plan])


def _run_query(query: str, *, session_id: str = "session-1", store: TTLSessionMemoryStore | None = None):
    active_store = store or TTLSessionMemoryStore()
    with patch.dict("os.environ", {"AGENT_RUNTIME_MODE": "loop", "NL_PARSER_MODE": "rule"}, clear=False), patch(
        "app.services.task_orchestrator.session_memory_store",
        active_store,
    ), patch(
        "app.services.task_orchestrator.get_or_create_user_profile",
        return_value=ProfileMemory(user_id="user-1", default_location="广州", default_task_type="inspection"),
    ), patch(
        "app.services.task_orchestrator.AgentLoop.run",
        _run_with_planner_only,
    ), patch(
        "app.services.task_orchestrator.update_profile_from_parsed",
    ), patch(
        "app.services.task_orchestrator._with_conversation_record",
        side_effect=lambda **kwargs: kwargs["response"],
    ):
        return orchestrate_task_query(query, session_id=session_id, user_id="user-1")


def _tool_results(response):
    return response.result["tool_results"]


def test_mixed_orchestration_evaluate_uses_risk_tool():
    response = _run_query("深圳明天下午2点到5点适合做无人机巡检吗")

    assert response.intent == "evaluate"
    assert list(_tool_results(response)) == ["evaluate_flight_risk"]
    assert response.agent_runtime["plan_actions"] == ["call_tool"]


def test_mixed_orchestration_recommend_uses_recommend_tool():
    response = _run_query("广州未来72小时什么时候最适合航测")

    assert response.intent == "recommend"
    assert list(_tool_results(response)) == ["recommend_flight_windows"]


def test_mixed_orchestration_compare_uses_compare_tool():
    response = _run_query("深圳、广州和珠海明天下午哪个更适合低空巡航")

    assert response.intent == "compare"
    assert list(_tool_results(response)) == ["compare_flight_locations"]


def test_mixed_orchestration_history_skips_rag_and_uses_history_tool():
    response = _run_query("查一下我上次深圳任务记录")
    result = _tool_results(response)["query_user_history"]["data"]

    assert response.intent == "history"
    assert list(_tool_results(response)) == ["query_user_history"]
    assert result["metadata"]["rag_decision"] == "skip_rag"


def test_mixed_orchestration_knowledge_uses_rag_tool():
    response = _run_query("深圳无人机巡检政策有什么要注意")
    result = _tool_results(response)["query_knowledge_snippets"]["data"]

    assert response.intent == "knowledge"
    assert list(_tool_results(response)) == ["query_knowledge_snippets"]
    assert result["metadata"]["rag_decision"] == "use_rag"


def test_mixed_orchestration_missing_fields_asks_clarification_and_saves_pending():
    store = TTLSessionMemoryStore()
    response = _run_query("明天下午能飞吗", store=store)
    pending = store.get("session-1", user_id="user-1")

    assert response.success is False
    assert response.intent == "evaluate"
    assert response.agent_runtime["plan_actions"] == ["ask_clarification"]
    assert "任务地点" in response.message
    assert pending["pending_task"]["missing_fields"] == ["location"]


def test_mixed_orchestration_modify_recomputes_state_from_session():
    store = TTLSessionMemoryStore()
    store.set(
        "session-1",
        {
            "intent": "evaluate",
            "location": "深圳",
            "date": "2026-08-03",
            "start_time": "13:00",
            "end_time": "18:00",
            "task_type": "inspection",
        },
        user_id="user-1",
    )

    response = _run_query("地点改成广州", store=store)
    result = _tool_results(response)["evaluate_flight_risk"]["data"]

    assert response.intent == "evaluate"
    assert result["tool_input"]["location"] == "广州"
    assert result["tool_input"]["date"] == "2026-08-03"
    assert response.agent_runtime["context_merge"]["modified_fields"] == ["location"]
