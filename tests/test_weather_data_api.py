from task_api_helpers import versioned_task_payload

from datetime import timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app.db.models import MissionTask, TaskRequest
from app.services.session_memory import TTLSessionMemoryStore
from app.services.weather.client import HttpClient
from app.utils.timezone import now_in_app_timezone


@pytest.fixture
def weather_api(api_client, api_session_factory, monkeypatch, tmp_path):
    for key, value in {
        "AGENT_RUNTIME_MODE": "loop", "NL_PARSER_MODE": "rule", "LLM_ENABLED": "false",
        "QWEATHER_API_KEY": "test-only", "QWEATHER_MAX_RETRIES": "2", "QWEATHER_RETRY_BACKOFF_SECONDS": "0",
    }.items():
        monkeypatch.setenv(key, value)
    for module in ("profile_memory", "conversation_history", "agent_trace", "history_query", "history_persistence"):
        monkeypatch.setattr(f"app.services.{module}.SessionLocal", api_session_factory)
    memory = TTLSessionMemoryStore()
    monkeypatch.setattr("app.services.task_orchestrator.session_memory_store", memory)
    monkeypatch.setattr("app.services.bm25_knowledge_store.DEFAULT_INDEX_DIR", tmp_path)
    day = (now_in_app_timezone().date() + timedelta(days=1)).isoformat()
    state = {"fault": None, "calls": [], "bad_location": None}

    def transport(request):
        state["calls"].append(request.url.path)
        if request.url.path.endswith("/lookup"):
            location = request.url.params["location"]
            return httpx.Response(200, json={"code": "200", "location": [
                {"id": location, "name": location, "lat": "22.54", "lon": "114.05"}
            ]})
        if request.url.path.endswith("/72h"):
            fault = "missing" if request.url.params["location"] == state["bad_location"] else state["fault"]
            if fault == "timeout":
                raise httpx.ReadTimeout("fixture timeout", request=request)
            hours = [{"fxTime": f"{day}T{hour}:00:00+08:00", "text": "晴", "windSpeed": "5",
                      "windScale": "1-2", "humidity": "50", "precip": "0", "pop": "0"} for hour in (14, 15, 16)]
            if fault == "missing":
                hours[1].pop("pop")
            elif fault == "invalid":
                hours[1]["windSpeed"] = "NaN"
            elif fault == "gap":
                hours.pop(1)
            elif fault == "empty":
                hours = []
            elif fault == "outside":
                hours = [{**hour, "fxTime": hour["fxTime"].replace(day, "2099-01-01")} for hour in hours]
            elif fault == "optional":
                hours[0].update(temp=None, cloud=None, pressure=None)
            elif fault == "bad_time":
                hours[0]["fxTime"] = "bad-time"
            return httpx.Response(200, json={"code": "200", "hourly": hours})
        if state["fault"] == "warnings":
            raise httpx.ReadTimeout("warning service unavailable", request=request)
        return httpx.Response(200, json={"metadata": {}, "alerts": []})

    original_init = HttpClient.__init__

    def install(self, **kwargs):
        original_init(self, **kwargs)
        self._client.close()
        self._client = httpx.Client(transport=httpx.MockTransport(transport))

    monkeypatch.setattr(HttpClient, "__init__", install)
    credentials = {"username": "weather-validation", "password": "weather-validation-test-password"}
    assert api_client.post("/auth/register", json=credentials).status_code == 201
    token = api_client.post("/auth/login", json=credentials).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    request = {"location": "深圳", "date": day, "start_time": "14:00", "end_time": "17:00", "task_type": "cruise"}
    query = f"深圳{day}下午2点到5点巡航能飞吗"
    return api_client, api_session_factory, headers, state, memory, request, query


@pytest.mark.parametrize("fault,code,status", [
    ("missing", "WEATHER_DATA_INCOMPLETE", 502), ("invalid", "WEATHER_DATA_INVALID", 502),
    ("gap", "WEATHER_DATA_INCOMPLETE", 502), ("empty", "WEATHER_DATA_INCOMPLETE", 502),
    ("outside", "WEATHER_FORECAST_OUT_OF_RANGE", 422),
    ("bad_time", "WEATHER_DATA_INVALID", 502),
])
def test_structured_assessment_reports_unavailable_data_without_a_decision(weather_api, fault, code, status):
    client, factory, _, state, _, request, _ = weather_api
    state["fault"] = fault
    response = client.post("/cruise/evaluate", json=request)
    assert response.status_code == status, response.text
    body = response.json()
    assert body["success"] is False and body["error_code"] == code
    assert "无法完成评估" in body["message"]
    assert "advice" not in body
    # Invalid data must fail before an unrelated warning API call or a snapshot write.
    assert len(state["calls"]) == 2
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(TaskRequest)) == 0


def test_missing_display_metrics_does_not_prevent_assessment(weather_api):
    client, _, _, state, _, request, _ = weather_api
    state["fault"] = "optional"
    response = client.post("/cruise/evaluate", json=request)
    assert response.status_code == 200, response.text
    assert response.json()["advice"]["overall_decision"] == "适飞"


def test_failed_city_override_is_retained_for_retry_and_trace_without_replacing_history(weather_api):
    client, factory, headers, state, memory, _, query = weather_api
    first = client.post("/agent/query", json={"query": query, "session_id": "retry"}, headers=headers).json()
    assert first["success"] is True, first
    history = client.get(f"/cruise/history/{first['request_id']}", headers=headers).json()
    state["fault"] = "gap"
    failed = client.post("/agent/query", json={"query": "换成广州", "session_id": "retry"}, headers=headers).json()
    assert failed["success"] is False and failed["request_id"] is None
    assert failed["fallback"]["error_code"] == "WEATHER_DATA_INCOMPLETE"
    assert failed["fallback"]["details"] and failed["fallback"]["retryable"]
    assert failed["agent_runtime"]["fallback_used"] is False
    context = memory.get("retry", user_id=failed["user_id"])
    assert context["location"] == "深圳"
    assert context["pending_task"]["parsed"]["location"] == "广州"
    trace = client.get(f"/agent/traces/{failed['trace_id']}", headers=headers).json()
    assert trace["outcome"] == "failed" and trace["request_ids"] == []
    assert {"error", "tool_call", "tool_result", "final_response"} <= {event["event_type"] for event in trace["events"]}
    assert any(event["error_code"] == "WEATHER_DATA_INCOMPLETE" for event in trace["events"])
    assert client.get(f"/cruise/history/{first['request_id']}", headers=headers).json() == history
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(TaskRequest)) == 1
    state["fault"] = None
    retried = client.post("/agent/query", json={"query": "重试", "session_id": "retry"}, headers=headers).json()
    assert retried["success"] is True, retried
    assert retried["parsed"]["location"] == "广州"
    assert retried["parsed"]["start_time"] == "14:00" and retried["parsed"]["end_time"] == "17:00"
    assert retried["trace_id"] != failed["trace_id"]
    assert "pending_task" not in memory.get("retry", user_id=failed["user_id"])


@pytest.mark.parametrize("fault", ["timeout", "warnings"])
def test_provider_or_warning_failure_stops_and_retains_inputs(weather_api, fault):
    client, _, headers, state, memory, _, query = weather_api
    state["fault"] = fault
    response = client.post("/agent/query", json={"query": query, "session_id": "outage"}, headers=headers).json()
    assert response["success"] is False and response["request_id"] is None
    assert response["fallback"]["error_code"] == "WeatherRequestError"
    assert response["agent_runtime"]["fallback_used"] is False
    assert memory.get("outage", user_id=response["user_id"])["pending_task"]["parsed"]["location"] == "深圳"
    assert sum(path.endswith("/72h") for path in state["calls"]) == (2 if fault == "timeout" else 1)
    trace = client.get(f"/agent/traces/{response['trace_id']}", headers=headers).json()
    assert trace["outcome"] == "failed"


def test_legacy_runtime_retains_weather_inputs_for_manual_retry(weather_api, monkeypatch):
    client, _, headers, state, _, _, query = weather_api
    monkeypatch.setenv("AGENT_RUNTIME_MODE", "legacy")
    state["fault"] = "missing"
    failed = client.post("/agent/query", json={"query": query, "session_id": "legacy-retry"}, headers=headers).json()
    assert failed["success"] is False and failed["fallback"]["error_code"] == "WEATHER_DATA_INCOMPLETE"
    state["fault"] = None
    retried = client.post("/agent/query", json={"query": "重试", "session_id": "legacy-retry"}, headers=headers).json()
    assert retried["success"] is True, retried
    assert retried["parsed"]["location"] == "深圳" and retried["parsed"]["start_time"] == "14:00"


def test_recommendation_rejects_gaps_in_the_returned_scan(weather_api):
    client, _, _, state, _, request, _ = weather_api
    payload = {"location": request["location"], "date": request["date"], "scan_hours": 72, "min_window_hours": 2}
    assert client.post("/cruise/recommend", json=payload).status_code == 200
    state["fault"] = "gap"
    failed = client.post("/cruise/recommend", json=payload)
    assert failed.status_code == 502 and "recommendation" not in failed.json()


def test_comparison_does_not_recommend_an_unavailable_location(weather_api):
    client, _, _, state, _, request, _ = weather_api
    payload = {**request, "locations": ["深圳", "广州"]}
    state["bad_location"] = "广州"
    partial = client.post("/cruise/compare", json=payload)
    assert partial.status_code == 200, partial.text
    result = partial.json()
    assert result["recommended_location"]["location"] == "深圳"
    assert [x["location"] for x in result["top_k_locations"]] == ["深圳"]
    unavailable = next(x for x in result["comparisons"] if x["location"] == "广州")
    assert unavailable["available"] is False and "缺少降水概率" in unavailable["error_message"]
    state["fault"] = "gap"
    none = client.post("/cruise/compare", json=payload).json()
    assert none["recommended_location"] is None and none["top_k_locations"] == []


def test_task_failure_keeps_the_last_successful_snapshot_and_status(weather_api):
    client, factory, headers, state, _, request, _ = weather_api
    task = client.post("/tasks", json={"title": "weather data check", **request}, headers=headers).json()
    task_id = task["id"]
    assert client.post(f"/tasks/{task_id}/evaluate", json=versioned_task_payload(client, task_id, headers), headers=headers).status_code == 200
    with factory() as db:
        record = db.get(MissionTask, task_id)
        before = (record.status, record.latest_request_id, record.latest_decision)
    state["fault"] = "missing"
    failed = client.post(f"/tasks/{task_id}/evaluate", json=versioned_task_payload(client, task_id, headers), headers=headers)
    assert failed.status_code == 502, failed.text
    with factory() as db:
        record = db.get(MissionTask, task_id)
        assert (record.status, record.latest_request_id, record.latest_decision) == before
        assert db.scalar(select(func.count()).select_from(TaskRequest)) == 1


def test_task_retry_targets_the_failed_task_instead_of_the_previously_completed_task(weather_api):
    client, factory, headers, state, _, request, _ = weather_api
    first = client.post("/tasks", json={"title": "first task", **request}, headers=headers).json()["id"]
    second = client.post("/tasks", json={"title": "second task", **request, "location": "广州"}, headers=headers).json()["id"]
    first_run = client.post("/agent/query", json={"query": f"评估任务{first}", "session_id": "tasks"}, headers=headers).json()
    assert first_run["success"] is True, first_run
    state["fault"] = "missing"
    failed = client.post("/agent/query", json={"query": f"评估任务{second}", "session_id": "tasks"}, headers=headers).json()
    assert failed["success"] is False and failed["fallback"]["error_code"] == "WEATHER_DATA_INCOMPLETE"
    state["fault"] = None
    retried = client.post("/agent/query", json={"query": "重试", "session_id": "tasks"}, headers=headers).json()
    assert retried["success"] is True, retried
    assert retried["parsed"]["task_id"] == second
    with factory() as db:
        assert db.get(MissionTask, first).latest_request_id == first_run["request_id"]
        assert db.get(MissionTask, second).latest_request_id == retried["request_id"]
        assert db.scalar(select(func.count()).select_from(TaskRequest)) == 2
