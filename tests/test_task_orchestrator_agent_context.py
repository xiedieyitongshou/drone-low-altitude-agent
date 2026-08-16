from unittest.mock import patch

from app.agent import AgentLoopResult, ToolResult, mark_completed, record_tool_result
from app.services.profile_memory import ProfileMemory
from app.services.session_memory import TTLSessionMemoryStore
from app.services.task_orchestrator import orchestrate_task_query


def test_loop_mode_saves_pending_task_without_using_profile_location():
    store = TTLSessionMemoryStore()
    profile = ProfileMemory(user_id="user-1", default_location="广州", default_task_type="inspection")

    with patch.dict("os.environ", {"AGENT_RUNTIME_MODE": "loop", "NL_PARSER_MODE": "rule"}, clear=False), patch(
        "app.services.task_orchestrator.session_memory_store",
        store,
    ), patch(
        "app.services.task_orchestrator.get_or_create_user_profile",
        return_value=profile,
    ), patch(
        "app.services.task_orchestrator._with_conversation_record",
        side_effect=lambda **kwargs: kwargs["response"],
    ):
        response = orchestrate_task_query("明天下午能飞吗", session_id="session-1", user_id="user-1")

    pending = store.get("session-1", user_id="user-1")
    assert response.success is False
    assert response.intent == "evaluate"
    assert response.fallback["errors"] == []
    assert "任务地点" in response.fallback["message"]
    assert response.parsed["task_type"] == "inspection"
    assert "location" not in response.parsed
    assert pending["pending_task"]["missing_fields"] == ["location"]
    assert pending["pending_task"]["parsed"]["task_type"] == "inspection"


def test_loop_mode_merges_second_turn_user_input_with_pending_task():
    store = TTLSessionMemoryStore()
    store.set(
        "session-1",
        {
            "pending_task": {
                "intent": "evaluate",
                "parsed": {
                    "date": "2026-08-03",
                    "start_time": "13:00",
                    "end_time": "18:00",
                    "task_type": "inspection",
                    "purpose": "明天下午能飞吗",
                },
                "missing_fields": ["location"],
                "query": "明天下午能飞吗",
            },
            "intent": "evaluate",
            "date": "2026-08-03",
            "start_time": "13:00",
            "end_time": "18:00",
            "task_type": "inspection",
        },
        user_id="user-1",
    )
    captured = {}

    def fake_run(self, state, context):
        captured["state"] = state
        completed = record_tool_result(
            state,
            tool_name="evaluate_flight_risk",
            tool_result=ToolResult(success=True, tool_name="evaluate_flight_risk", data={"overall_decision": "适飞"}),
        )
        completed = mark_completed(completed, message="done")
        return AgentLoopResult(success=True, final_state=completed, message="done", output={"ok": True})

    with patch.dict("os.environ", {"AGENT_RUNTIME_MODE": "loop", "NL_PARSER_MODE": "rule"}, clear=False), patch(
        "app.services.task_orchestrator.session_memory_store",
        store,
    ), patch(
        "app.services.task_orchestrator.get_or_create_user_profile",
        return_value=ProfileMemory(user_id="user-1", default_location="广州", default_task_type="cruise"),
    ), patch(
        "app.services.task_orchestrator.AgentLoop.run",
        fake_run,
    ), patch(
        "app.services.task_orchestrator.update_profile_from_parsed",
    ), patch(
        "app.services.task_orchestrator._with_conversation_record",
        side_effect=lambda **kwargs: kwargs["response"],
    ):
        response = orchestrate_task_query("深圳", session_id="session-1", user_id="user-1")

    task_draft = captured["state"].task_draft
    assert response.success is True
    assert response.context_used is True
    assert task_draft["location"] == "深圳"
    assert task_draft["date"] == "2026-08-03"
    assert task_draft["start_time"] == "13:00"
    assert task_draft["task_type"] == "inspection"


def test_loop_mode_recomputes_state_when_user_modifies_location():
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
    captured = {}

    def fake_run(self, state, context):
        captured["state"] = state
        completed = record_tool_result(
            state,
            tool_name="evaluate_flight_risk",
            tool_result=ToolResult(success=True, tool_name="evaluate_flight_risk", data={"overall_decision": "适飞"}),
        )
        completed = mark_completed(completed, message="done")
        return AgentLoopResult(success=True, final_state=completed, message="done", output={"ok": True})

    with patch.dict("os.environ", {"AGENT_RUNTIME_MODE": "loop", "NL_PARSER_MODE": "rule"}, clear=False), patch(
        "app.services.task_orchestrator.session_memory_store",
        store,
    ), patch(
        "app.services.task_orchestrator.get_or_create_user_profile",
        return_value=ProfileMemory(user_id="user-1", default_location="广州", default_task_type="cruise"),
    ), patch(
        "app.services.task_orchestrator.AgentLoop.run",
        fake_run,
    ), patch(
        "app.services.task_orchestrator.update_profile_from_parsed",
    ), patch(
        "app.services.task_orchestrator._with_conversation_record",
        side_effect=lambda **kwargs: kwargs["response"],
    ):
        response = orchestrate_task_query("地点改成广州", session_id="session-1", user_id="user-1")

    task_draft = captured["state"].task_draft
    context_merge = response.agent_runtime["context_merge"]
    assert response.success is True
    assert task_draft["location"] == "广州"
    assert task_draft["date"] == "2026-08-03"
    assert context_merge["modified_fields"] == ["location"]
    assert context_merge["invalidated_tools"] == ["evaluate_flight_risk", "query_knowledge_snippets"]


def test_loop_mode_saves_current_task_context_after_tool_success():
    store = TTLSessionMemoryStore()

    def fake_run(self, state, context):
        completed = record_tool_result(
            state,
            tool_name="create_mission_task",
            tool_result=ToolResult(
                success=True,
                tool_name="create_mission_task",
                data={
                    "id": "task-1",
                    "title": "深圳湾巡检",
                    "status": "draft",
                    "location": "深圳湾",
                },
            ),
        )
        completed = mark_completed(completed, message="done")
        return AgentLoopResult(success=True, final_state=completed, message="done", output={"ok": True})

    with patch.dict("os.environ", {"AGENT_RUNTIME_MODE": "loop", "NL_PARSER_MODE": "rule"}, clear=False), patch(
        "app.services.task_orchestrator.session_memory_store",
        store,
    ), patch(
        "app.services.task_orchestrator.get_or_create_user_profile",
        return_value=ProfileMemory(user_id="user-1", default_task_type="inspection"),
    ), patch(
        "app.services.task_orchestrator.AgentLoop.run",
        fake_run,
    ), patch(
        "app.services.task_orchestrator.update_profile_from_parsed",
    ), patch(
        "app.services.task_orchestrator._with_conversation_record",
        side_effect=lambda **kwargs: kwargs["response"],
    ):
        response = orchestrate_task_query("帮我创建一个深圳湾明天下午巡检任务", session_id="session-1", user_id="user-1")

    saved = store.get("session-1", user_id="user-1")
    assert response.success is True
    assert response.intent == "create_task"
    assert response.parsed["current_task_id"] == "task-1"
    assert saved["current_task_id"] == "task-1"
    assert saved["current_task_title"] == "深圳湾巡检"


def test_legacy_mode_dispatches_mission_task_intent_to_tool_registry():
    store = TTLSessionMemoryStore()

    with patch.dict("os.environ", {"AGENT_RUNTIME_MODE": "legacy", "NL_PARSER_MODE": "rule"}, clear=False), patch(
        "app.services.task_orchestrator.session_memory_store",
        store,
    ), patch(
        "app.services.task_orchestrator.get_or_create_user_profile",
        return_value=ProfileMemory(user_id="user-1", default_task_type="inspection"),
    ), patch(
        "app.services.task_orchestrator.default_tool_registry.call",
        return_value=ToolResult(
            success=True,
            tool_name="create_mission_task",
            data={
                "id": "task-legacy-1",
                "title": "深圳湾巡检",
                "status": "draft",
                "location": "深圳湾",
            },
        ),
    ) as call_tool, patch(
        "app.services.task_orchestrator.update_profile_from_parsed",
    ), patch(
        "app.services.task_orchestrator._with_conversation_record",
        side_effect=lambda **kwargs: kwargs["response"],
    ):
        response = orchestrate_task_query("帮我创建一个深圳湾明天下午巡检任务", session_id="session-1", user_id="user-1")

    saved = store.get("session-1", user_id="user-1")
    assert response.success is True
    assert response.intent == "create_task"
    assert response.result["id"] == "task-legacy-1"
    assert response.parsed["current_task_id"] == "task-legacy-1"
    assert saved["current_task_id"] == "task-legacy-1"
    call_tool.assert_called_once()
    assert call_tool.call_args.args[0] == "create_mission_task"
