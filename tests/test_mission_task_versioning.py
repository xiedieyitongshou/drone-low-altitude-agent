from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import event, func, select

from app.db.models import (
    AgentTraceEventRecord, CruiseAssessment, MissionTask, OperationRequest, TaskRequest, User, WeatherProviderSnapshot,
)
from app.schemas import (
    MissionTaskCreateRequest, MissionTaskRecommendRequest, MissionTaskSelectWindowRequest,
    MissionTaskStatusUpdateRequest, MissionTaskUpdateRequest,
)
from app.services.mission_task_execution import (
    evaluate_mission_task, preflight_check_mission_task, recommend_mission_task_windows, select_mission_task_window,
)
from app.services.mission_task_management import (
    create_mission_task, get_mission_task_detail, update_mission_task, update_mission_task_status,
)
from app.services.mission_task_versioning import MissionTaskVersionConflictError
from app.services.task_orchestrator import orchestrate_task_query
from test_mission_task_execution_api import build_artifacts, build_recommendation
from test_task_creation_idempotency import operation_client, operation_factory, headers  # noqa: F401


def create(factory):
    with factory() as db:
        return create_mission_task(db=db, current_user=db.get(User, "owner"), payload=MissionTaskCreateRequest(
            title="Version audit", location="Shenzhen Bay", date="2026-08-18",
            start_time="14:00", end_time="16:00", task_type="inspection",
        ))


def read(factory, task_id):
    with factory() as db:
        return get_mission_task_detail(db=db, current_user=db.get(User, "owner"), task_id=task_id)


def status(factory, task_id, version, target="cancelled"):
    with factory() as db:
        return update_mission_task_status(db=db, current_user=db.get(User, "owner"), task_id=task_id,
                                         payload=MissionTaskStatusUpdateRequest(status=target, expected_version=version))


def edit(factory, task_id, version, **values):
    with factory() as db:
        return update_mission_task(db=db, current_user=db.get(User, "owner"), task_id=task_id,
                                   payload=MissionTaskUpdateRequest(expected_version=version, **values))


def count(factory, model):
    with factory() as db:
        return db.scalar(select(func.count()).select_from(model))


def run_long(factory, task_id, version, action):
    with factory() as db:
        user = db.get(User, "owner")
        if action == "recommend":
            return recommend_mission_task_windows(db=db, current_user=user, task_id=task_id,
                                                  payload=MissionTaskRecommendRequest(expected_version=version, scan_hours=24))
        handler = preflight_check_mission_task if action == "preflight" else evaluate_mission_task
        return handler(db=db, current_user=user, task_id=task_id, expected_version=version)


def query(factory, text, key, session_id="version-session"):
    with factory() as db:
        return orchestrate_task_query(text, user_id="owner", session_id=session_id, db=db, idempotency_key=key)


@pytest.mark.parametrize("action", ["evaluate", "preflight", "recommend"])
@pytest.mark.parametrize("change", ["cancel", "location", "time", "title"])
def test_long_result_cannot_overwrite_an_intervening_change(operation_factory, monkeypatch, action, change):
    task = create(operation_factory)
    if action == "preflight":
        task = status(operation_factory, task.id, task.version, "scheduled")
    base = task.version

    def compute(request):
        if change == "cancel":
            changed = status(operation_factory, task.id, base)
        else:
            values = {"location": "Beijing"} if change == "location" else (
                {"start_time": "16:00", "end_time": "18:00"} if change == "time" else {"title": "Renamed"})
            changed = edit(operation_factory, task.id, base, **values)
        assert changed.version == base + 1
        return build_recommendation(request) if action == "recommend" else build_artifacts(request)

    dependency = "build_recommendation_response" if action == "recommend" else "evaluate_cruise_request_with_artifacts"
    monkeypatch.setattr(f"app.services.mission_task_execution.{dependency}", compute)
    with pytest.raises(MissionTaskVersionConflictError):
        run_long(operation_factory, task.id, base, action)
    current = read(operation_factory, task.id)
    assert current.version == base + 1
    assert current.status == ("cancelled" if change == "cancel" else task.status if change == "title" else "draft")
    assert current.latest_request_id is None
    assert "latest_recommendation" not in current.metadata
    for model in (TaskRequest, CruiseAssessment, WeatherProviderSnapshot, AgentTraceEventRecord):
        assert count(operation_factory, model) == 0


def test_change_after_final_read_is_still_caught_by_atomic_update(operation_factory, monkeypatch):
    task = create(operation_factory)
    monkeypatch.setattr("app.services.mission_task_execution.evaluate_cruise_request_with_artifacts", build_artifacts)
    with operation_factory() as db:
        fired = []

        def cancel_just_before_flush(session, context, instances):
            if not fired:
                fired.append(True)
                status(operation_factory, task.id, task.version)

        event.listen(db, "before_flush", cancel_just_before_flush)
        with pytest.raises(MissionTaskVersionConflictError):
            evaluate_mission_task(db=db, current_user=db.get(User, "owner"), task_id=task.id, expected_version=task.version)
    assert fired
    assert read(operation_factory, task.id).status == "cancelled"
    assert count(operation_factory, TaskRequest) == 0


def test_failed_history_write_rolls_back_task_version_and_result(operation_factory, monkeypatch):
    task = create(operation_factory)
    monkeypatch.setattr("app.services.mission_task_execution.evaluate_cruise_request_with_artifacts", build_artifacts)
    monkeypatch.setattr("app.services.mission_task_execution._persist_cruise_evaluation", Mock(side_effect=RuntimeError("injected storage failure")))
    with pytest.raises(RuntimeError):
        run_long(operation_factory, task.id, task.version, "evaluate")
    current = read(operation_factory, task.id)
    assert current.version == task.version and current.status == "draft"
    assert current.latest_request_id is None
    assert count(operation_factory, TaskRequest) == 0


def test_critical_edit_invalidates_current_results_but_preserves_history(operation_factory, monkeypatch):
    task = create(operation_factory)
    monkeypatch.setattr("app.services.mission_task_execution.evaluate_cruise_request_with_artifacts", build_artifacts)
    monkeypatch.setattr("app.services.mission_task_execution.build_recommendation_response", build_recommendation)
    assessment = run_long(operation_factory, task.id, task.version, "evaluate")
    assessed = read(operation_factory, task.id)
    assert assessed.version == 2
    assert assessment.request["input_task_version"] == 1 and assessment.request["task_version"] == 2
    with operation_factory() as db:
        saved = db.scalar(select(TaskRequest).where(TaskRequest.task_id == task.id))
        assert saved.raw_request_json["input_task_version"] == 1
    renamed = edit(operation_factory, task.id, assessed.version, title="New title")
    assert renamed.status == "evaluated" and renamed.latest_request_id == assessed.latest_request_id
    recommendation = run_long(operation_factory, task.id, renamed.version, "recommend")
    with operation_factory() as db:
        selected = select_mission_task_window(db=db, current_user=db.get(User, "owner"), task_id=task.id,
            payload=MissionTaskSelectWindowRequest(rank=1, expected_version=recommendation.request["task_version"]))
    checked = run_long(operation_factory, task.id, selected.version, "preflight")
    changed = edit(operation_factory, task.id, checked.request["task_version"], location="Beijing")
    assert changed.version == checked.request["task_version"] + 1
    assert changed.status == "draft" and changed.latest_request_id is None and changed.latest_decision is None
    assert changed.latest_trace_id is None and changed.selected_window is None
    detail = read(operation_factory, task.id)
    assert "latest_recommendation" not in detail.metadata and "latest_preflight_check" not in detail.metadata
    assert len(detail.request_ids) == 2
    assert count(operation_factory, CruiseAssessment) == 2


def test_repeated_cancel_is_safe_but_a_stale_cancel_cannot_override_completion(operation_factory):
    task = create(operation_factory)
    scheduled = status(operation_factory, task.id, task.version, "scheduled")
    completed = status(operation_factory, task.id, scheduled.version, "completed")
    with pytest.raises(MissionTaskVersionConflictError):
        status(operation_factory, task.id, scheduled.version)
    assert read(operation_factory, task.id).status == "completed"
    another = create(operation_factory)
    cancelled = status(operation_factory, another.id, another.version)
    again = status(operation_factory, another.id, another.version)
    assert again.version == cancelled.version and again.status == "cancelled"


def test_two_short_writes_on_one_version_only_one_succeeds(operation_factory, monkeypatch):
    task = create(operation_factory)
    barrier = Barrier(2)
    from app.services.mission_task_management import _get_owned_task

    def simultaneous(**kwargs):
        loaded = _get_owned_task(**kwargs)
        barrier.wait(timeout=10)
        return loaded

    monkeypatch.setattr("app.services.mission_task_management._get_owned_task", simultaneous)

    def submit(title):
        try:
            return edit(operation_factory, task.id, task.version, title=title).version
        except MissionTaskVersionConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ("A", "B")))
    assert results.count(2) == 1 and results.count("conflict") == 1
    assert read(operation_factory, task.id).version == 2


@pytest.mark.parametrize("method,suffix,payload", [
    ("patch", "", {"title": "change"}), ("patch", "/status", {"status": "cancelled"}),
    ("post", "/evaluate", {}), ("post", "/recommend", {}),
    ("post", "/preflight-check", {}), ("post", "/select-window", {"rank": 1}),
])
def test_every_http_write_requires_the_version_the_client_read(operation_client, operation_factory, method, suffix, payload):
    task = create(operation_factory)
    response = getattr(operation_client, method)(f"/tasks/{task.id}{suffix}", headers=headers(), json=payload)
    assert response.status_code == 428
    assert response.json()["error_code"] == "TASK_VERSION_REQUIRED"
    assert read(operation_factory, task.id).version == 1


def test_http_stale_version_is_a_specific_conflict(operation_client, operation_factory):
    task = create(operation_factory)
    changed = operation_client.patch(f"/tasks/{task.id}", headers=headers(), json={"title": "new", "expected_version": task.version})
    assert changed.status_code == 200 and changed.json()["version"] == 2
    response = operation_client.patch(f"/tasks/{task.id}/status", headers=headers(), json={"status": "cancelled", "expected_version": task.version})
    assert response.status_code == 409 and response.json()["error_code"] == "TASK_VERSION_CONFLICT"
    assert read(operation_factory, task.id).status == "draft"


def test_old_recommendation_rank_cannot_select_from_a_replacement_list(operation_factory, monkeypatch):
    task = create(operation_factory)
    monkeypatch.setattr("app.services.mission_task_execution.build_recommendation_response", build_recommendation)
    first = run_long(operation_factory, task.id, task.version, "recommend")
    second = run_long(operation_factory, task.id, first.request["task_version"], "recommend")
    with operation_factory() as db, pytest.raises(MissionTaskVersionConflictError):
        select_mission_task_window(db=db, current_user=db.get(User, "owner"), task_id=task.id,
                                  payload=MissionTaskSelectWindowRequest(rank=1, expected_version=first.request["task_version"]))
    assert read(operation_factory, task.id).version == second.request["task_version"]
    assert read(operation_factory, task.id).selected_window is None


@pytest.mark.parametrize("mode", ["loop", "legacy"])
def test_agent_conflict_stops_without_replaying_and_clears_old_windows(operation_factory, monkeypatch, mode):
    monkeypatch.setenv("AGENT_RUNTIME_MODE", mode)
    monkeypatch.setattr("app.services.mission_task_execution.build_recommendation_response", build_recommendation)
    created = query(operation_factory, "帮我创建一个深圳湾明天下午巡检任务", "create")
    task_id = created.parsed["current_task_id"]
    first = query(operation_factory, "推荐窗口", "recommend")
    assert first.success and first.parsed["current_task_version"] == 2
    # Another client replaces the list after the Agent has shown its old list.
    run_long(operation_factory, task_id, 2, "recommend")
    failed = query(operation_factory, "就选第一个窗口", "select")
    assert not failed.success and failed.fallback["error_code"] == "TASK_VERSION_CONFLICT"
    assert not (failed.agent_runtime or {}).get("fallback_used")
    again = query(operation_factory, "就选第一个窗口", "select")
    assert again.model_dump(mode="json") == failed.model_dump(mode="json")
    assert read(operation_factory, task_id).selected_window is None
    from app.services.task_orchestrator import session_memory_store
    context = session_memory_store.get("version-session", user_id="owner")
    assert "current_task_version" not in context and "last_recommended_windows" not in context
    refreshed = query(operation_factory, "推荐窗口", "new-recommend")
    assert refreshed.success and refreshed.parsed["current_task_version"] == 4
    selected = query(operation_factory, "就选第一个窗口", "new-select")
    assert selected.success and selected.parsed["current_task_version"] == 5


def test_agent_retry_after_interrupted_commit_cannot_upgrade_its_bound_version(operation_factory, monkeypatch):
    created = query(operation_factory, "帮我创建一个深圳湾明天下午巡检任务", "create")
    task_id = created.parsed["current_task_id"]
    weather = Mock(side_effect=build_artifacts)
    monkeypatch.setattr("app.services.mission_task_execution.evaluate_cruise_request_with_artifacts", weather)
    with patch("app.services.task_orchestrator._save_completed_context", side_effect=SystemExit("after task commit")):
        with pytest.raises(SystemExit):
            query(operation_factory, "评估一下这个任务", "assessment")
    assert read(operation_factory, task_id).version == 2
    failed = query(operation_factory, "评估一下这个任务", "assessment")
    assert not failed.success and failed.fallback["error_code"] == "TASK_VERSION_CONFLICT"
    assert weather.call_count == 1 and count(operation_factory, TaskRequest) == 1


def test_legacy_creation_receipt_has_no_fabricated_current_version(operation_factory):
    with operation_factory() as db:
        request = MissionTaskCreateRequest(title="Old receipt")
        first = create_mission_task(db=db, current_user=db.get(User, "owner"), payload=request, idempotency_key="old")
        receipt = db.scalar(select(OperationRequest).where(OperationRequest.idempotency_key == "old"))
        frozen = dict(receipt.response_json)
        frozen.pop("version")
        receipt.response_json = frozen
        db.commit()
    edit(operation_factory, first.id, 1, title="Later title")
    with operation_factory() as db:
        replay = create_mission_task(db=db, current_user=db.get(User, "owner"), payload=request, idempotency_key="old")
    assert replay.version is None
    assert read(operation_factory, first.id).version == 2


def test_conflict_context_is_cleared_before_releasing_session_lock(operation_factory, monkeypatch):
    created = query(operation_factory, "帮我创建一个深圳湾明天下午巡检任务", "create")
    task_id = created.parsed["current_task_id"]
    status(operation_factory, task_id, 1)
    from app.services.task_orchestrator import _clear_stale_task_context
    from app.services.session_execution import session_execution_guard
    checked = []

    def clear(response):
        with operation_factory() as db, session_execution_guard(user_id="owner", session_id="version-session", db=db) as admitted:
            assert admitted is False
            checked.append(True)
        _clear_stale_task_context(response)

    monkeypatch.setattr("app.services.task_orchestrator._clear_stale_task_context", clear)
    result = query(operation_factory, "评估一下这个任务", "evaluate")
    assert not result.success and checked
    assert read(operation_factory, task_id).status == "cancelled"


@pytest.mark.parametrize("weather_retry", [False, True])
def test_switching_tasks_cannot_reuse_the_previous_tasks_window_list(operation_factory, monkeypatch, weather_retry):
    monkeypatch.setattr("app.services.mission_task_execution.build_recommendation_response", build_recommendation)
    monkeypatch.setattr("app.services.mission_task_execution.evaluate_cruise_request_with_artifacts", build_artifacts)
    query(operation_factory, "帮我创建一个深圳湾明天下午巡检任务", "first-create")
    assert query(operation_factory, "推荐窗口", "first-recommend").success
    second = create(operation_factory)
    # A different client has generated a recommendation for the other task.
    run_long(operation_factory, second.id, 1, "recommend")
    if weather_retry:
        from app.services.weather.exceptions import WeatherRequestError
        with patch("app.services.mission_task_execution.evaluate_cruise_request_with_artifacts", side_effect=WeatherRequestError("injected")):
            assert not query(operation_factory, f"评估任务{second.id}", "failed-second-evaluate").success
        evaluated = query(operation_factory, "重试", "second-evaluate")
    else:
        evaluated = query(operation_factory, f"评估任务{second.id}", "second-evaluate")
    assert evaluated.success and evaluated.parsed["current_task_version"] == 3
    failed = query(operation_factory, "就选第一个窗口", "wrong-list")
    assert not failed.success and failed.fallback["error_code"] == "TASK_VERSION_CONFLICT"
    assert read(operation_factory, second.id).selected_window is None
