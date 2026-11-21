import json
import os
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import func, select

from app.db.models import TaskRequest
from app.agent import AgentPlan, AgentPlanAction
from app.services.session_memory import TTLSessionMemoryStore
from app.services.weather.client import HttpClient
from app.utils.timezone import now_in_app_timezone


@pytest.fixture
def traced_agent(api_client, api_session_factory, monkeypatch, tmp_path):
    for name, value in {
        "AGENT_RUNTIME_MODE": "loop", "NL_PARSER_MODE": "rule", "LLM_ENABLED": "false",
        "KNOWLEDGE_RETRIEVER": "bm25", "QWEATHER_API_KEY": "test-only",
        "QWEATHER_MAX_RETRIES": "2", "QWEATHER_RETRY_BACKOFF_SECONDS": "0",
    }.items():
        monkeypatch.setenv(name, value)
    for module in ("profile_memory", "conversation_history", "agent_trace", "history_query"):
        monkeypatch.setattr(f"app.services.{module}.SessionLocal", api_session_factory)
    monkeypatch.setattr("app.services.task_orchestrator.session_memory_store", TTLSessionMemoryStore())
    monkeypatch.setattr("app.services.bm25_knowledge_store.DEFAULT_INDEX_DIR", tmp_path)
    day = (now_in_app_timezone().date() + timedelta(days=1)).isoformat()
    transport_state = {"calls": [], "fault": None}

    def transport(request):
        transport_state["calls"].append(request.url.path)
        if request.url.path.endswith("/lookup"):
            return httpx.Response(200, json={"code": "200", "location": [
                {"id": "fixed", "name": "深圳", "lat": "22.54", "lon": "114.05"}
            ]})
        if request.url.path.endswith("/72h"):
            if transport_state["fault"] == "timeout":
                raise httpx.ReadTimeout("fixed timeout", request=request)
            return httpx.Response(200, json={"code": "200", "updateTime": f"{day}T13:00:00+08:00", "hourly": [
                {"fxTime": f"{day}T14:00:00+08:00", "text": "晴", "temp": "20", "windSpeed": "20",
                 "windScale": "1-2", "humidity": "50", "precip": "0", "pop": "0"}
            ]})
        return httpx.Response(200, json={"metadata": {"timestamp": f"{day}T13:00:00+08:00"}, "alerts": []})

    original_init = HttpClient.__init__

    def install_transport(self, **kwargs):
        original_init(self, **kwargs)
        self._client.close()
        self._client = httpx.Client(transport=httpx.MockTransport(transport))

    monkeypatch.setattr(HttpClient, "__init__", install_transport)
    return api_client, api_session_factory, f"深圳{day}下午2点到3点巡航能飞吗", transport_state


def login(client, username):
    credentials = {"username": username, "password": "isolated-trace-test-password"}
    assert client.post("/auth/register", json=credentials).status_code == 201
    token = client.post("/auth/login", json=credentials).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def capture(name, **data):
    directory = os.getenv("TRACE_VALIDATION_OUTPUT")
    if directory:
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        (path / f"{name}.json").write_text(json.dumps({
            "weather_source": "fixed_httpx_mock_transport", **data,
        }, ensure_ascii=False, indent=2), encoding="utf-8")


def test_evaluation_history_conversation_and_trace_form_one_owned_record(traced_agent):
    client, factory, query, state = traced_agent
    owner = login(client, "trace-owner")
    other = login(client, "trace-other")
    response = client.post("/agent/query", json={"query": query, "session_id": "trace-session"}, headers=owner)
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True, {"parsed": payload["parsed"], "fallback": payload["fallback"]}
    request_id, trace_id = payload["request_id"], payload["trace_id"]
    assert request_id and trace_id == payload["agent_runtime"]["trace_id"]
    computed = payload["result"]["tool_results"]["evaluate_flight_risk"]["data"]
    assert computed["request"]["request_id"] == request_id
    assert computed["request"]["trace_id"] == trace_id
    assert payload["composed"]["overall_decision"] == computed["advice"]["overall_decision"]

    history = client.get(f"/cruise/history/{request_id}", headers=owner).json()
    assert history["trace_id"] == trace_id
    assert history["advice"] == computed["advice"]
    conversation = client.get(f"/agent/conversations/{payload['conversation_id']}", headers=owner).json()
    assert conversation["request_id"] == request_id
    assert conversation["trace_id"] == trace_id
    assert conversation["response"]["conversation_id"] == payload["conversation_id"]
    assert conversation["response"]["agent_runtime"]["timings"] == payload["agent_runtime"]["timings"]

    trace = client.get(f"/agent/traces/{trace_id}", headers=owner).json()
    assert trace["request_ids"] == [request_id]
    assert trace["conversation_ids"] == [payload["conversation_id"]]
    assert trace["outcome"] == "success"
    assert trace["timings"] == payload["agent_runtime"]["timings"]
    kinds = [item["event_type"] for item in trace["events"]]
    assert {"parse", "plan", "tool_call", "tool_result", "final_response", "stage"} <= set(kinds)
    assert kinds[-1] == "final_response" and kinds.count("final_response") == 1
    assert [item["step_index"] for item in trace["events"]] == list(range(1, len(kinds) + 1))
    stages = trace["timings"]["stages"]
    assert {"parser", "planner", "tool", "weather", "weather_http", "rules", "history_write", "composition"} <= stages.keys()
    assert stages["weather_http"]["calls"] == len(state["calls"]) == 3
    assert all(item["duration_ms"] >= item["self_ms"] >= 0 for item in stages.values())
    assert client.get(f"/agent/traces/{trace_id}", headers=other).status_code == 404
    assert client.get(f"/cruise/history/{request_id}", headers=other).status_code == 404
    assert client.get(f"/cruise/history/{request_id}").status_code == 401
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(TaskRequest)) == 1
    capture("evaluation", response=payload, history=history, conversation=conversation, trace=trace)


def test_clarification_is_queryable_without_a_tool_and_continuation_has_its_own_trace(traced_agent):
    client, _, _, state = traced_agent
    owner = login(client, "trace-clarification")
    payload = client.post("/agent/query", json={"query": "明天下午2点到3点能飞吗", "session_id": "pending"}, headers=owner).json()
    trace = client.get(f"/agent/traces/{payload['trace_id']}", headers=owner).json()
    assert payload["success"] is False
    assert trace["outcome"] == "clarification"
    assert state["calls"] == []
    assert trace["request_ids"] == []
    assert trace["conversation_ids"] == [payload["conversation_id"]]
    kinds = {item["event_type"] for item in trace["events"]}
    assert {"parse", "plan", "clarification", "final_response"} <= kinds
    assert "tool_call" not in kinds
    completed = client.post("/agent/query", json={"query": "深圳", "session_id": "pending"}, headers=owner).json()
    assert completed["success"] is True
    assert completed["trace_id"] != payload["trace_id"]
    assert completed["request_id"]
    capture("clarification", response=payload, trace=trace, continuation=completed)


def test_timeout_records_retry_count_failure_and_final_response(traced_agent):
    client, _, query, state = traced_agent
    owner = login(client, "trace-timeout")
    state["fault"] = "timeout"
    payload = client.post("/agent/query", json={"query": query}, headers=owner).json()
    trace = client.get(f"/agent/traces/{payload['trace_id']}", headers=owner).json()
    assert payload["success"] is False and payload["request_id"] is None
    assert trace["outcome"] == "failed" and trace["request_ids"] == []
    assert {"fallback", "error", "final_response"} <= {item["event_type"] for item in trace["events"]}
    assert trace["timings"]["stages"].get("weather_http", {}).get("calls") == 3, payload["fallback"]
    assert trace["timings"]["stages"]["weather_http"]["failures"] == 2
    assert len(state["calls"]) == 3
    assert payload["agent_runtime"]["fallback_used"] is False
    capture("timeout", response=payload, trace=trace)


@pytest.mark.parametrize("failure", ["history", "composition", "conversation", "trace"])
def test_auxiliary_failures_do_not_replay_or_replace_a_computed_decision(traced_agent, failure):
    client, factory, query, state = traced_agent
    owner = login(client, f"trace-{failure}-failure")
    target = {
        "history": "app.agent.tools.persist_cruise_evaluation",
        "composition": "app.services.response_composer.retrieve_knowledge_by_request",
        "conversation": "app.services.task_orchestrator.persist_conversation_record",
        "trace": "app.services.agent_trace.record_trace_events",
    }[failure]
    with patch(target, side_effect=RuntimeError("injected save failure")):
        payload = client.post("/agent/query", json={"query": query}, headers=owner).json()
    assert payload["success"] is True
    computed = payload["result"]["tool_results"]["evaluate_flight_risk"]["data"]
    assert computed["advice"]["overall_decision"] == payload["composed"]["overall_decision"] == "慎飞"
    assert payload["warnings"] and len(state["calls"]) == 3
    assert payload["agent_runtime"]["fallback_used"] is False
    assert bool(payload["request_id"]) is (failure != "history")
    assert bool(payload["conversation_id"]) is (failure != "conversation")
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(TaskRequest)) == (0 if failure == "history" else 1)
    if failure != "trace":
        trace = client.get(f"/agent/traces/{payload['trace_id']}", headers=owner).json()
        assert trace["outcome"] == "degraded"
        assert trace["events"][-1]["event_type"] == "final_response"
        capture(f"failure-{failure}", response=payload, trace=trace)


def test_existing_llm_client_reports_its_timing_inside_parser(traced_agent, monkeypatch):
    client, _, _, _ = traced_agent
    owner = login(client, "trace-llm")
    for key, value in {"NL_PARSER_MODE": "llm", "LLM_ENABLED": "true", "LLM_PROVIDER": "openai_compatible",
                       "LLM_MODEL": "test-model", "LLM_API_KEY": "test-only", "LLM_BASE_URL": "https://llm.invalid"}.items():
        monkeypatch.setenv(key, value)

    def post(request):
        return httpx.Response(200, request=request, json={"choices": [{"message": {
            "content": json.dumps({"intent": "knowledge", "city": "深圳", "knowledge_evidence": {"city": "深圳"}})
        }}]})

    monkeypatch.setattr("app.services.llm_client.httpx", SimpleNamespace(
        Client=lambda **kwargs: httpx.Client(transport=httpx.MockTransport(post), **kwargs),
        HTTPError=httpx.HTTPError, HTTPStatusError=httpx.HTTPStatusError,
    ))
    payload = client.post("/agent/query", json={"query": "深圳报备政策"}, headers=owner).json()
    assert payload["success"] is True
    trace = client.get(f"/agent/traces/{payload['trace_id']}", headers=owner).json()
    stages = trace["timings"]["stages"]
    assert stages["llm"]["calls"] == 1
    assert stages["llm"]["failures"] == 0
    assert stages["parser"]["duration_ms"] >= stages["llm"]["duration_ms"]
    capture("llm-timing", response=payload, trace=trace, llm_source="mocked_http_post")


def test_legacy_fallback_shares_trace_and_saves_only_one_evaluation(traced_agent):
    client, factory, query, state = traced_agent
    owner = login(client, "trace-legacy-fallback")
    with patch("app.agent.loop.plan_next_step", return_value=AgentPlan(action=AgentPlanAction.FALLBACK, reason="injected pre-tool fallback")):
        payload = client.post("/agent/query", json={"query": query}, headers=owner).json()
    assert payload["success"] is True
    assert payload["agent_runtime"]["fallback_used"] is True
    trace = client.get(f"/agent/traces/{payload['trace_id']}", headers=owner).json()
    assert trace["request_ids"] == [payload["request_id"]]
    assert trace["outcome"] == "degraded"
    assert trace["events"][-1]["status_after"] == "completed"
    assert all(item["trace_id"] == payload["trace_id"] for item in trace["events"])
    assert "fallback" in {item["event_type"] for item in trace["events"]}
    assert len(state["calls"]) == 3
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(TaskRequest)) == 1
    capture("legacy-fallback", response=payload, trace=trace)
