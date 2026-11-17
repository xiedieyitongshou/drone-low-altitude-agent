from unittest.mock import patch

import pytest

from app.agent import (
    AgentLoopResult,
    AgentPlanAction,
    ToolResult,
    build_agent_fallback_output,
    build_clarification_message,
    default_tool_registry,
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


@pytest.fixture
def agent_api(api_client, api_session_factory, monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_RUNTIME_MODE", "loop")
    monkeypatch.setenv("NL_PARSER_MODE", "rule")
    monkeypatch.setenv("KNOWLEDGE_RETRIEVER", "bm25")
    monkeypatch.setenv("KNOWLEDGE_SOURCE_PATH", "data/knowledge/advice_rules.json")
    monkeypatch.setattr("app.services.bm25_knowledge_store.DEFAULT_INDEX_DIR", tmp_path)
    monkeypatch.setattr("app.services.task_orchestrator.session_memory_store", TTLSessionMemoryStore())
    monkeypatch.setattr("app.services.profile_memory.SessionLocal", api_session_factory)
    monkeypatch.setattr("app.services.conversation_history.SessionLocal", api_session_factory)
    monkeypatch.setattr("app.services.agent_trace.SessionLocal", api_session_factory)
    return api_client


def _login(client, username):
    credentials = {"username": username, "password": "agent-workflow-test-password"}
    assert client.post("/auth/register", json=credentials).status_code == 201
    token = client.post("/auth/login", json=credentials).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("parser_mode", ["rule", "hybrid"])
def test_agent_query_passes_original_question_and_city_to_rag(agent_api, monkeypatch, parser_mode):
    monkeypatch.setenv("NL_PARSER_MODE", parser_mode)
    headers = _login(agent_api, "rag-query-test")
    query = "深圳无人机作业报备政策有哪些注意事项？"

    with (
        patch("app.services.task_orchestrator.parse_natural_language_request_with_llm") as llm_parser,
        patch.object(default_tool_registry, "call", wraps=default_tool_registry.call) as call_tool,
    ):
        response = agent_api.post("/agent/query", json={"query": query}, headers=headers)

    llm_parser.assert_not_called()
    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "knowledge"
    assert payload["parsed"]["city"] == "深圳"
    tool_name, tool_input = call_tool.call_args.args
    assert tool_name == "query_knowledge_snippets"
    assert tool_input["query"] == query
    assert tool_input["city"] == "深圳"
    result = payload["result"]["tool_results"]["query_knowledge_snippets"]["data"]
    search_text = result["retrieval_metadata"]["attempts"][0]["query"]
    assert f"用户问题: {query}" in search_text
    assert "任务地区: 深圳" in search_text.splitlines()
    assert result["snippets"][0]["id"] == "policy-shenzhen-airspace-check-001"


def test_knowledge_city_stays_in_its_session_and_does_not_fill_flight_location(agent_api):
    owner_headers = _login(agent_api, "knowledge-owner")
    other_headers = _login(agent_api, "knowledge-other")
    for headers in (owner_headers, other_headers):
        assert agent_api.patch("/users/me/profile", json={"default_location": "深圳"}, headers=headers).status_code == 200

    for query, expected_city, source, headers in (
        ("广州，报备政策", "广州", "user_input", owner_headers),
        ("政策", "广州", "session", owner_headers),
        ("政策", "深圳", "profile", other_headers),
        ("改成深圳", "深圳", "user_input", owner_headers),
    ):
        response = agent_api.post("/agent/query", json={"query": query, "session_id": "same-id"}, headers=headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["intent"] == "knowledge"
        assert payload["agent_runtime"]["context_merge"]["field_sources"]["city"] == source
        data = payload["result"]["tool_results"]["query_knowledge_snippets"]["data"]
        assert f"任务地区: {expected_city}" in data["retrieval_metadata"]["attempts"][0]["query"].splitlines()

    evaluation = agent_api.post(
        "/agent/query", json={"query": "明天下午能飞吗", "session_id": "same-id"}, headers=owner_headers
    ).json()
    assert evaluation["intent"] == "evaluate"
    assert evaluation["agent_runtime"]["plan_actions"] == ["ask_clarification"]
    assert "location" not in evaluation["parsed"]


def test_create_task_merges_profile_defaults_before_checking_missing_fields(agent_api):
    headers = _login(agent_api, "create-with-profile")
    profile = {"default_task_type": "inspection", "default_start_time": "14:00", "default_end_time": "17:00"}
    assert agent_api.patch("/users/me/profile", json=profile, headers=headers).status_code == 200

    response = agent_api.post(
        "/agent/query", json={"query": "帮我创建一个深圳湾明天任务", "session_id": "create"}, headers=headers
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    sources = payload["agent_runtime"]["context_merge"]["field_sources"]
    task = payload["result"]["tool_results"]["create_mission_task"]["data"]
    assert (task["start_time"], task["end_time"], task["task_type"]) == ("14:00", "17:00", "inspection")
    assert sources["start_time"] == sources["end_time"] == sources["task_type"] == "profile"

    pending = agent_api.post(
        "/agent/query", json={"query": "帮我创建一个明天任务", "session_id": "create"}, headers=headers
    ).json()
    assert pending["success"] is False
    assert pending["agent_runtime"]["plan_actions"] == ["ask_clarification"]
    assert "任务地点" in pending["message"]

    completed = agent_api.post(
        "/agent/query", json={"query": "深圳湾9点到11点测绘", "session_id": "create"}, headers=headers
    ).json()
    assert completed["success"] is True
    assert completed["intent"] == "create_task"
    sources = completed["agent_runtime"]["context_merge"]["field_sources"]
    task = completed["result"]["tool_results"]["create_mission_task"]["data"]
    assert (task["location"], task["start_time"], task["end_time"], task["task_type"]) == (
        "深圳湾", "09:00", "11:00", "survey"
    )
    assert sources["date"] == "session"
    assert sources["start_time"] == sources["end_time"] == sources["task_type"] == "user_input"


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
