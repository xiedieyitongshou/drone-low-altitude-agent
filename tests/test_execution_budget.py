"""Deadline fault injection; all business data lives in isolated test databases."""

from threading import Event
from time import perf_counter

import httpx
import pytest
from sqlalchemy import func, select

from app.agent import ToolExecutionContext, ToolRegistry, default_tool_registry
from app.db.models import MissionTask, OperationRequest, User
from app.services.execution_budget import (
    BoundedExecutionPool, ExecutionBudget, ExecutionCapacityError, ExecutionTimeout,
    budgeted_sleep, current_budget, use_execution_budget,
)
from app.services.idempotency import agent_operation
from app.services.mission_task_management import create_mission_task
from app.services.mission_task_versioning import task_write_transaction
from app.services.nl_parser import ParsedTaskRequest
from app.services.run_observability import measure_stage, observe_run
from app.services.session_memory import TTLSessionMemoryStore
from app.services.task_orchestrator import _recover_committed_creation, orchestrate_task_query
from app.services.weather.client import HttpClient
from app.services.weather.exceptions import WeatherRequestError
from app.schemas import MissionTaskCreateRequest
from test_task_creation_idempotency import operation_factory  # noqa: F401


@pytest.fixture
def controlled_pools(monkeypatch):
    pools = {kind: BoundedExecutionPool(max_workers=2, name=f"test-{kind}")
             for kind in ("request", "tool", "cleanup")}
    monkeypatch.setattr("app.agent.tools.execution_pool", pools.__getitem__)
    monkeypatch.setattr("app.services.task_orchestrator.execution_pool", pools.__getitem__)
    yield pools
    for pool in pools.values():
        pool.shutdown()


def registry(handler, timeout_ms=30):
    tools = ToolRegistry()
    spec = default_tool_registry.get("create_mission_task").spec.model_copy(update={"timeout_ms": timeout_ms})
    tools.register(spec, handler)
    return tools


def call(tools, db, title="Deadline test"):
    return tools.call("create_mission_task", {"title": title},
                      context=ToolExecutionContext(user_id="owner", role="user", db=db))


def count(factory, model):
    with factory() as db:
        return db.scalar(select(func.count()).select_from(model))


def test_late_creation_cannot_commit_and_uses_an_owned_session(operation_factory, controlled_pools):
    released, finished = Event(), Event()
    original = default_tool_registry.get("create_mission_task").handler
    worker_sessions = []

    def slow(payload, context):
        worker_sessions.append(context.db)
        try:
            released.wait(1)
            return original(payload, context)
        finally:
            finished.set()

    try:
        with operation_factory() as db, agent_operation("late-create"):
            result = call(registry(slow), db)
            assert not result.success and result.error_code == "TOOL_TIMEOUT"
            assert worker_sessions and worker_sessions[0] is not db
            assert not finished.is_set()
        released.set()
        controlled_pools["tool"].shutdown()
        assert count(operation_factory, MissionTask) == 0
        assert count(operation_factory, OperationRequest) == 0
    finally:
        released.set()


@pytest.mark.parametrize("flush_before_timeout", [False, True])
def test_late_update_rolls_back_without_changing_task_version(operation_factory, controlled_pools, flush_before_timeout):
    released = Event()
    with operation_factory() as db:
        task = create_mission_task(db=db, current_user=db.get(User, "owner"),
                                   payload=MissionTaskCreateRequest(title="Original"))

    def late_update(payload, context):
        with task_write_transaction(context.db):
            row = context.db.get(MissionTask, task.id)
            row.title = "Expired update"
            if flush_before_timeout:
                context.db.flush()
            released.wait(1)
            if not flush_before_timeout:
                context.db.flush()
        return {"updated": True}

    try:
        with operation_factory() as db:
            result = call(registry(late_update), db)
        assert result.error_code == "TOOL_TIMEOUT"
        released.set()
        controlled_pools["tool"].shutdown()
        with operation_factory() as db:
            saved = db.get(MissionTask, task.id)
            assert saved.title == "Original" and saved.version == task.version
    finally:
        released.set()


def test_post_commit_tool_timeout_keeps_existing_idempotent_recovery(operation_factory, controlled_pools):
    released, committed = Event(), Event()
    original = default_tool_registry.get("create_mission_task").handler

    def lose_response(payload, context):
        response = original(payload, context)
        committed.set()
        released.wait(1)
        return response

    try:
        with operation_factory() as db, agent_operation("committed-timeout"):
            result = call(registry(lose_response, timeout_ms=150), db)
            assert committed.is_set()
            assert result.error_code == "TOOL_TIMEOUT"
            db.rollback()
            recovered = _recover_committed_creation(user_id="owner", session_id=None, db=db)
            assert recovered.success and recovered.agent_runtime["idempotency_recovered"]
            replay = call(default_tool_registry, db)
            assert replay.success and replay.data["id"] == recovered.parsed["task_id"]
        assert count(operation_factory, MissionTask) == 1
    finally:
        released.set()


def test_consecutive_timeouts_keep_capacity_until_workers_really_exit():
    pool = BoundedExecutionPool(max_workers=2, name="timeout-capacity")
    released = Event()
    started = []

    def slow():
        started.append(True)
        released.wait(1)

    try:
        for _ in range(2):
            with pytest.raises(ExecutionTimeout):
                pool.run(slow, ExecutionBudget.start(25))
        with pytest.raises(ExecutionCapacityError):
            pool.run(slow, ExecutionBudget.start(1000))
        assert len(started) == 2
    finally:
        released.set()
        pool.shutdown()


def test_explicit_tool_context_cannot_extend_the_active_request_deadline(controlled_pools):
    released = Event()
    tools = registry(lambda *args: released.wait(1), timeout_ms=2000)
    try:
        with use_execution_budget(ExecutionBudget.start(30)):
            result = tools.call("create_mission_task", {}, context=ToolExecutionContext(
                user_id="owner", budget=ExecutionBudget.start(2000)))
        assert result.error_code == "REQUEST_DEADLINE_EXCEEDED"
    finally:
        released.set()


def test_cancelled_tool_context_returns_error_without_running_the_handler(controlled_pools):
    called = []
    budget = ExecutionBudget.start(2000)
    budget.cancel()
    result = registry(lambda *args: called.append(True)).call("create_mission_task", {},
        context=ToolExecutionContext(user_id="owner", budget=budget))
    assert result.error_code == "REQUEST_DEADLINE_EXCEEDED" and called == []


def test_parser_and_tool_share_request_budget_and_do_not_save_late_context(
    operation_factory, monkeypatch, controlled_pools,
):
    from app.services import task_orchestrator

    released, entered = Event(), Event()
    seen_remaining = []
    memory = TTLSessionMemoryStore()
    memory.set("budget-session", {"city": "Original city"}, user_id="owner")
    monkeypatch.setenv("AGENT_REQUEST_TIMEOUT_MS", "300")
    monkeypatch.setattr(task_orchestrator, "get_or_create_user_profile", lambda _: None)
    monkeypatch.setattr(task_orchestrator, "session_memory_store", memory)

    def parse(*args, **kwargs):
        budgeted_sleep(0.1)
        return ParsedTaskRequest(intent="create_task", target_endpoint="/tasks", warnings=[], parsed={
            "task_title": "Budget task", "location": "Shenzhen", "date": "2026-11-26",
            "start_time": "14:00", "end_time": "17:00", "task_type": "inspection",
        })

    def slow(payload, context):
        seen_remaining.append(context.budget.remaining_seconds())
        entered.set()
        released.wait(1)
        return {"late": True}

    monkeypatch.setattr(task_orchestrator, "_parse_task_query", parse)
    original = default_tool_registry.get("create_mission_task")
    monkeypatch.setitem(default_tool_registry._tools, "create_mission_task",
                        type(original)(spec=original.spec, handler=slow))
    started = perf_counter()
    try:
        with operation_factory() as db:
            response = orchestrate_task_query("Create a task", user_id="owner", session_id="budget-session",
                                               db=db, idempotency_key="request-budget")
        assert entered.is_set()
        assert not response.success
        assert response.fallback["error_code"] == "REQUEST_DEADLINE_EXCEEDED"
        assert 0 < seen_remaining[0] < 0.22  # Parsing consumed the same budget.
        assert perf_counter() - started < 0.8
        released.set()
        controlled_pools["request"].shutdown()
        controlled_pools["tool"].shutdown()
        assert memory.get("budget-session", user_id="owner") == {"city": "Original city"}
        assert count(operation_factory, MissionTask) == 0
        with operation_factory() as db:
            assert all(receipt.response_json is None for receipt in db.scalars(select(OperationRequest)))
    finally:
        released.set()


def test_expired_parser_cannot_start_business_tools(operation_factory, monkeypatch, controlled_pools):
    from app.services import task_orchestrator

    released = Event()
    called = []
    monkeypatch.setenv("AGENT_REQUEST_TIMEOUT_MS", "80")
    monkeypatch.setattr(task_orchestrator, "get_or_create_user_profile", lambda _: None)

    def parse(*args, **kwargs):
        released.wait(1)
        return ParsedTaskRequest(intent="create_task", target_endpoint="/tasks", warnings=[], parsed={
            "task_title": "Late parse", "location": "Shenzhen", "date": "2026-11-26",
            "start_time": "14:00", "end_time": "17:00", "task_type": "inspection",
        })

    original = default_tool_registry.get("create_mission_task")
    monkeypatch.setattr(task_orchestrator, "_parse_task_query", parse)
    monkeypatch.setitem(default_tool_registry._tools, "create_mission_task",
                        type(original)(spec=original.spec, handler=lambda *args: called.append(True)))
    try:
        with operation_factory() as db:
            response = orchestrate_task_query("Create a task", user_id="owner", db=db)
        assert response.fallback["error_code"] == "REQUEST_DEADLINE_EXCEEDED"
        released.set()
        controlled_pools["request"].shutdown()
        assert called == []
        assert count(operation_factory, MissionTask) == 0
    finally:
        released.set()


def test_request_timeout_after_creation_recovers_without_replaying_parser(
    operation_factory, monkeypatch, controlled_pools,
):
    from app.services import task_orchestrator

    released, committed = Event(), Event()
    memory = TTLSessionMemoryStore()
    memory.set("recovery-session", {"city": "Original"}, user_id="owner")
    monkeypatch.setenv("AGENT_REQUEST_TIMEOUT_MS", "400")
    monkeypatch.setattr(task_orchestrator, "session_memory_store", memory)
    monkeypatch.setattr(task_orchestrator, "get_or_create_user_profile", lambda _: None)
    monkeypatch.setattr(task_orchestrator, "_parse_task_query", lambda *args, **kwargs: ParsedTaskRequest(
        intent="create_task", target_endpoint="/tasks", warnings=[], parsed={
            "task_title": "Committed task", "location": "Shenzhen", "date": "2026-11-26",
            "start_time": "14:00", "end_time": "17:00", "task_type": "inspection",
        }))
    save = task_orchestrator._save_completed_context

    def late_save(*args, **kwargs):
        committed.set()
        released.wait(2)
        return save(*args, **kwargs)

    monkeypatch.setattr(task_orchestrator, "_save_completed_context", late_save)

    def query():
        with operation_factory() as db:
            return orchestrate_task_query("Create a task", user_id="owner", session_id="recovery-session",
                                           db=db, idempotency_key="committed-request-timeout")

    try:
        failed = query()
        assert committed.is_set() and failed.fallback["error_code"] == "REQUEST_DEADLINE_EXCEEDED"
        assert count(operation_factory, MissionTask) == 1
        released.set()
        controlled_pools["request"].shutdown()
        controlled_pools["request"] = BoundedExecutionPool(max_workers=2, name="recovery-request")
        assert memory.get("recovery-session", user_id="owner") == {"city": "Original"}

        def unexpected(*args, **kwargs):
            raise AssertionError("Committed creation recovery must skip the parser")

        monkeypatch.setattr(task_orchestrator, "_parse_task_query", unexpected)
        recovered = query()
        assert recovered.success and recovered.agent_runtime["idempotency_recovered"]
        replayed = query()
        assert replayed.model_dump(mode="json") == recovered.model_dump(mode="json")
        assert count(operation_factory, MissionTask) == 1
    finally:
        released.set()


@pytest.mark.parametrize("budget_ms, expected_attempts, expected_error", [
    (100, 2, ExecutionTimeout), (1000, 3, WeatherRequestError),
])
def test_weather_retries_and_backoff_consume_one_budget(
    monkeypatch, budget_ms, expected_attempts, expected_error,
):
    clock, timeouts = [10.0], []
    monkeypatch.setattr("app.services.execution_budget.monotonic", lambda: clock[0])
    client = HttpClient(api_key="fixture-only", timeout_seconds=1, max_retries=3, retry_backoff_seconds=0.01)

    def request(url, **kwargs):
        timeouts.append(kwargs["timeout"])
        clock[0] += 0.04
        raise httpx.ReadTimeout("Injected timeout")

    def sleep(seconds):
        clock[0] += min(seconds, current_budget().remaining_seconds())
        current_budget().check()

    monkeypatch.setattr(client._client, "get", request)
    monkeypatch.setattr("app.services.weather.client.budgeted_sleep", sleep)
    try:
        with use_execution_budget(ExecutionBudget.start(budget_ms)), pytest.raises(expected_error):
            client.get("https://fixture.invalid/weather")
        assert len(timeouts) == expected_attempts
        assert timeouts[1] < timeouts[0]
        assert clock[0] <= 10 + budget_ms / 1000
    finally:
        client.close()


def test_llm_parser_does_not_retry_or_fallback_after_budget_exhaustion(monkeypatch):
    from app.services.task_orchestrator import _parse_task_query

    clock, calls = [10.0], []
    monkeypatch.setattr("app.services.execution_budget.monotonic", lambda: clock[0])
    monkeypatch.setenv("NL_PARSER_MODE", "hybrid")
    monkeypatch.setattr("app.services.llm_task_parser.is_llm_enabled", lambda: True)

    def generate(**kwargs):
        calls.append(True)
        clock[0] += 0.2
        return None

    monkeypatch.setattr("app.services.llm_task_parser.generate_text", generate)
    with use_execution_budget(ExecutionBudget.start(100)), pytest.raises(ExecutionTimeout):
        _parse_task_query("Create a task")
    assert calls == [True]


def test_llm_http_timeout_is_capped_by_remaining_budget(monkeypatch):
    from app.services.llm_client import LLMClientConfig, generate_text_or_raise

    clock, limits = [10.0], []
    monkeypatch.setattr("app.services.execution_budget.monotonic", lambda: clock[0])

    class Client:
        def __init__(self, *, timeout):
            limits.append(timeout)
            clock[0] += 0.02

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, **kwargs):
            limits.append(kwargs["timeout"])
            return httpx.Response(200, request=httpx.Request("POST", url),
                                  json={"choices": [{"message": {"content": "Fixture response"}}]})

    monkeypatch.setattr("app.services.llm_client.httpx.Client", Client)
    config = LLMClientConfig(enabled=True, provider="openai_compatible", model="fixture",
                             base_url="https://fixture.invalid", api_key="fixture-only",
                             timeout_seconds=20, max_tokens=10)
    with use_execution_budget(ExecutionBudget.start(100)):
        assert generate_text_or_raise(system_prompt="test", user_prompt="test", config=config) == "Fixture response"
    assert limits == pytest.approx([0.1, 0.08])


def test_late_tool_trace_cannot_mutate_completed_request(controlled_pools):
    released = Event()

    def late(payload, context):
        with measure_stage("weather"):
            released.wait(1)
        return {"late": True}

    try:
        with observe_run(user_id="owner", session_id=None) as observation:
            result = call(registry(late), None)
            assert result.error_code == "TOOL_TIMEOUT"
            before = [event.model_dump() for event in observation.events], list(observation.samples)
            released.set()
            controlled_pools["tool"].shutdown()
            assert ([event.model_dump() for event in observation.events], observation.samples) == before
            assert observation.stack == []
    finally:
        released.set()


def test_comparison_parallel_branches_share_budget_and_have_independent_timing(monkeypatch):
    from app.schemas import ComparedLocationResult, MultiLocationComparisonRequest
    from app.services.comparison import location_comparison

    budgets = []

    def evaluate(location, *args):
        budgets.append(current_budget())
        with measure_stage("weather"):
            budgeted_sleep(0.01)
        return ComparedLocationResult(rank=0, location=location, available=False)

    monkeypatch.setattr(location_comparison, "_evaluate_single_location", evaluate)
    budget = ExecutionBudget.start(1000)
    with use_execution_budget(budget), observe_run(user_id="owner", session_id=None) as observation:
        response = location_comparison.compare_locations(MultiLocationComparisonRequest(
            locations=["A", "B", "C", "D", "E", "F"], date="2026-11-26", start_time="14:00", end_time="17:00"))
    assert len(response.comparisons) == 6
    assert len(budgets) == 6 and all(item is budget for item in budgets)
    assert len(observation.samples) == 6 and observation.stack == []


def test_expired_comparison_does_not_start_more_location_branches(monkeypatch, controlled_pools):
    from app.schemas import ComparedLocationResult
    from app.services.comparison import location_comparison

    released, entered = Event(), []

    def evaluate(location, *args):
        entered.append(location)
        released.wait(1)
        return ComparedLocationResult(rank=0, location=location, available=False)

    monkeypatch.setattr(location_comparison, "_evaluate_single_location", evaluate)
    tools = ToolRegistry()
    spec = default_tool_registry.get("compare_flight_locations").spec.model_copy(update={"timeout_ms": 50})
    tools.register(spec, lambda payload, context: location_comparison.compare_locations(
        location_comparison.MultiLocationComparisonRequest.model_validate(payload)))
    try:
        result = tools.call("compare_flight_locations", {
            "locations": [str(index) for index in range(50)], "date": "2026-11-26",
            "start_time": "14:00", "end_time": "17:00",
        }, context=ToolExecutionContext(user_id="owner"))
        assert result.error_code == "TOOL_TIMEOUT"
        released.set()
        controlled_pools["tool"].shutdown()
        assert 0 < len(entered) <= 4
    finally:
        released.set()
