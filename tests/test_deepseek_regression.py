"""Manual live DeepSeek contract tests; launch via scripts/deepseek_regression_eval.py."""

from datetime import timedelta
import json
import os
from pathlib import Path

import pytest


pytestmark = [
    pytest.mark.deepseek_live,
    pytest.mark.skipif(not os.getenv("DEEPSEEK_EVAL_ISOLATED_ROOT"), reason="explicit isolated DeepSeek runner required"),
]


class RecordingCase:
    def __init__(self, name):
        self.name = name
        self.model_calls = []
        self.turns = []
        self.checks = []
        self.completed = False
        self.inject_invalid_format = False

    def check(self, name, condition):
        self.checks.append({"name": name, "passed": bool(condition)})
        assert condition, name


@pytest.fixture
def live_case(request, monkeypatch, tmp_path):
    from sqlalchemy import select
    from app.db.base import Base
    from app.db.models import User
    from app.db.session import engine, SessionLocal
    from app.services import llm_task_parser
    from app.services.weather import QWeatherService
    from app.utils.timezone import now_in_app_timezone

    isolation = Path(os.environ["DEEPSEEK_EVAL_ISOLATED_ROOT"]).resolve()
    # A direct pytest invocation must never inherit a business database.
    assert engine.url.drivername == "sqlite"
    assert Path(engine.url.database).resolve() == isolation / "regression.db"
    Base.metadata.create_all(engine)
    case = RecordingCase(request.node.name)
    case.user_id = request.node.name
    with SessionLocal() as db:
        if not db.scalar(select(User).where(User.id == case.user_id)):
            db.add(User(id=case.user_id, username=case.user_id, password_hash="isolated-no-login-account", role="user", is_active=True))
            db.commit()
    today = now_in_app_timezone().replace(hour=0, minute=0, second=0, microsecond=0)
    case.date = (today + timedelta(days=1)).date().isoformat()
    case.day_text = (today + timedelta(days=1)).strftime("%Y年%m月%d日")
    case.weather_calls = []

    class FixedWeather(QWeatherService):
        def __init__(self):
            pass

        def lookup_location_payload(self, location, number=1):
            case.weather_calls.append({"operation": "lookup", "location": location})
            return {"code": "200", "location": [{"id": location, "name": location, "lat": "22.54", "lon": "114.05"}]}

        def get_hourly_weather_payload(self, location_id, hours="72h"):
            case.weather_calls.append({"operation": "hourly", "location": location_id})
            return {"code": "200", "updateTime": today.isoformat(), "hourly": [
                {"fxTime": (today + timedelta(hours=index)).isoformat(), "temp": "20", "text": "晴",
                 "windSpeed": "5", "windScale": "1-2", "humidity": "50", "precip": "0", "pop": "0"}
                for index in range(121)
            ]}

        def get_weather_warning_payload(self, latitude, longitude):
            return {"metadata": {"zeroResult": True}, "alerts": []}

        def close(self):
            pass

    original_generate = llm_task_parser.generate_text

    def generate(**kwargs):
        content = original_generate(**kwargs)
        case.check("received_nonempty_real_model_response", isinstance(content, str) and bool(content.strip()))
        case.model_calls.append({"query": json.loads(kwargs["user_prompt"])["query"], "response": content,
                                 "format_fault_injected": case.inject_invalid_format})
        return "{deliberately invalid JSON" if case.inject_invalid_format else content

    monkeypatch.setattr(llm_task_parser, "generate_text", generate)
    monkeypatch.setattr("app.services.cruise_evaluator.QWeatherService", FixedWeather)
    monkeypatch.setattr("app.services.recommendation_executor.QWeatherService", FixedWeather)
    monkeypatch.setattr("app.services.response_explainer.generate_text", lambda **kwargs: None)
    monkeypatch.setattr("app.services.knowledge_reranker.generate_text", lambda **kwargs: None)
    monkeypatch.setattr("app.services.bm25_knowledge_store.DEFAULT_INDEX_DIR", tmp_path / "bm25")
    monkeypatch.setenv("NL_PARSER_MODE", "llm")
    try:
        yield case
    finally:
        report = {
            "run_id": os.environ["DEEPSEEK_EVAL_RUN_ID"], "case_id": case.name,
            "model_transport": os.getenv("DEEPSEEK_EVAL_MODEL_TRANSPORT", "deepseek"),
            "passed": case.completed and bool(case.checks) and all(check["passed"] for check in case.checks),
            "checks": case.checks, "model_calls": case.model_calls, "turns": case.turns,
            "weather_calls": case.weather_calls,
        }
        (Path(os.environ["DEEPSEEK_EVAL_REPORT_DIR"]) / f"case-{case.name}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
        )


def query(case, text, *, operation_id=None):
    from app.agent import default_tool_registry
    from app.db.session import SessionLocal
    from app.services.task_orchestrator import orchestrate_task_query
    from unittest.mock import patch

    inputs = []
    original = default_tool_registry.call

    def call(name, payload=None, **kwargs):
        inputs.append({"tool": name, "input": payload})
        return original(name, payload, **kwargs)

    with patch.object(default_tool_registry, "call", call), SessionLocal() as db:
        response = orchestrate_task_query(text, user_id=case.user_id, session_id=case.name,
                                          idempotency_key=operation_id, db=db)
    case.turns.append({"query": text, "tool_inputs": inputs, "response": response.model_dump(mode="json")})
    return response


def tool_data(case, response, tool):
    case.check("request_succeeded", response.success)
    case.check("real_model_parser_used", response.parser_source == "llm")
    case.check("runtime_completed", response.agent_runtime["status"] == "completed")
    results = (response.result or {}).get("tool_results", {})
    case.check("expected_tool_only", set(results) == {tool})
    case.check("tool_succeeded", results[tool]["success"])
    return results[tool]["data"]


def check_assessment(case, data, location, start="14:00", end="16:00", task_type="inspection"):
    request = data["request"]
    case.check("assessment_matches_parameters", all(request.get(key) == value for key, value in {
        "location": location, "date": case.date, "start_time": start, "end_time": end, "task_type": task_type,
    }.items()))
    case.check("fixed_weather_decision", data["advice"]["allow_cruise"] is True)
    case.check("has_hourly_result", bool(data["advice"]["hourly_assessment"]))


def test_deepseek_clarification_continuation(live_case):
    case = live_case
    first = query(case, f"{case.day_text}下午14:00到16:00适合做无人机巡检吗？")
    case.check("asks_location", first.agent_runtime["status"] == "needs_clarification"
               and set(first.fallback["missing_fields"]) == {"location"})
    case.check("does_not_execute_incomplete_request", not case.turns[-1]["tool_inputs"] and not case.weather_calls)
    second = query(case, "地点是深圳，其他条件不变")
    data = tool_data(case, second, "evaluate_flight_risk")
    check_assessment(case, data, "深圳")
    case.check("inherited_tool_arguments", all(case.turns[-1]["tool_inputs"][0]["input"].get(key) == value for key, value in {
        "location": "深圳", "date": case.date, "start_time": "14:00", "end_time": "16:00", "task_type": "inspection",
    }.items()))
    case.completed = True


def test_deepseek_modify_conditions(live_case):
    case = live_case
    first = query(case, f"深圳{case.day_text}14:00到16:00适合做无人机巡检吗？")
    check_assessment(case, tool_data(case, first, "evaluate_flight_risk"), "深圳")
    second = query(case, "地点改成广州，时间改成15:00到17:00，任务改成测绘，日期不变")
    check_assessment(case, tool_data(case, second, "evaluate_flight_risk"), "广州", "15:00", "17:00", "survey")
    case.check("parameters_overrode_prior_state", second.parsed["location"] == "广州" and second.parsed["task_type"] == "survey")
    case.check("evaluated_new_location", case.weather_calls[-2]["location"] == "广州")
    case.completed = True


def test_deepseek_task_operations(live_case):
    from sqlalchemy import func, select
    from app.db.models import MissionTask
    from app.db.session import SessionLocal

    case = live_case
    text = f"创建一个深圳{case.day_text}14:00到16:00的巡检任务"
    created = query(case, text, operation_id="live-create-once")
    data = tool_data(case, created, "create_mission_task")
    task_id = data["id"]
    case.check("task_created_as_draft", data["status"] == "draft" and data["user_id"] == case.user_id)
    calls = len(case.model_calls)
    retry = query(case, text, operation_id="live-create-once")
    case.check("idempotent_replay", retry.result == created.result and len(case.model_calls) == calls)
    previous_version = data["version"]
    for text, tool, status in (
        ("评估一下这个任务", "evaluate_mission_task", "evaluated"),
        ("给这个任务推荐窗口", "recommend_mission_task_windows", "evaluated"),
        ("选择第一个窗口", "select_mission_task_window", "scheduled"),
        ("执行前复核这个任务", "preflight_check_mission_task", "recheck"),
    ):
        response = query(case, text)
        data = tool_data(case, response, tool)
        case.check("current_task_argument", case.turns[-1]["tool_inputs"][0]["input"]["task_id"] == task_id)
        if tool == "recommend_mission_task_windows":
            case.check("has_recommended_windows", bool(data["recommendation"]["recommended_windows"]))
        elif tool == "evaluate_mission_task":
            check_assessment(case, data, "深圳")
        with SessionLocal() as db:
            task = db.get(MissionTask, task_id)
            case.check("database_status_and_version", task.status == status and task.version > previous_version)
            case.check("response_database_version_match", response.parsed["current_task_version"] == task.version)
            previous_version = task.version
            case.check("one_owned_task", db.scalar(select(func.count()).select_from(MissionTask).where(MissionTask.user_id == case.user_id)) == 1)
    case.check("preflight_conclusion_persisted", bool(data["advice"]["allow_cruise"]) and bool(data["request"]["request_id"]))
    case.completed = True


def test_deepseek_invalid_model_format(live_case):
    from sqlalchemy import func, select
    from app.db.models import TaskRequest
    from app.db.session import SessionLocal

    case = live_case
    case.inject_invalid_format = True
    response = query(case, f"深圳{case.day_text}14:00到16:00适合巡检吗？")
    case.check("malformed_output_not_executed", not response.success and not case.turns[-1]["tool_inputs"] and not case.weather_calls)
    case.check("structured_clarification", response.agent_runtime["status"] == "needs_clarification" and bool(response.fallback))
    with SessionLocal() as db:
        case.check("no_evaluation_write", db.scalar(select(func.count()).select_from(TaskRequest).where(TaskRequest.user_id == case.user_id)) == 0)
    case.completed = True


def test_deepseek_rule_fallback(live_case, monkeypatch):
    case = live_case
    monkeypatch.setenv("NL_PARSER_MODE", "hybrid")
    case.inject_invalid_format = True
    response = query(case, f"深圳{case.day_text}14:00到16:00适合巡检吗？")
    case.check("rule_fallback_reported", response.parser_source == "llm_fallback_rule")
    case.check("rule_fallback_succeeded", response.success and response.agent_runtime["status"] == "completed")
    check_assessment(case, response.result["tool_results"]["evaluate_flight_risk"]["data"], "深圳")
    case.check("real_model_fault_was_injected", bool(case.model_calls) and all(call["format_fault_injected"] for call in case.model_calls))
    case.completed = True
