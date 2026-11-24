from task_api_helpers import versioned_task_payload

from collections.abc import Generator
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import AgentTraceEventRecord, CruiseAssessment, MissionTask, TaskRequest, User
from app.dependencies import get_db
from app.rules import assess_cruise_window
from app.schemas import (
    CruiseAssessmentResponse,
    CruiseEvaluateRequest,
    LocationInfo,
    RecommendationRequest,
    RecommendationResponse,
    RecommendationResult,
    RecommendationStrategy,
    RecommendationWindow,
    RiskDecision,
    WarningDataBundle,
    WeatherDataBundle,
    WeatherHourData,
)
from app.services.auth_service import create_access_token, hash_password
from app.services.cruise_evaluator import CruiseEvaluationArtifacts
from main import app


def build_test_client() -> tuple[TestClient, dict[str, str], sessionmaker[Session]]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        db.add_all(
            [
                User(
                    id="user-a",
                    username="user_a",
                    password_hash=hash_password("demo123456"),
                    role="user",
                    is_active=True,
                ),
                User(
                    id="user-b",
                    username="user_b",
                    password_hash=hash_password("demo123456"),
                    role="user",
                    is_active=True,
                ),
            ]
        )
        db.commit()

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), {
        "user-a": create_access_token("user-a"),
        "user-b": create_access_token("user-b"),
    }, TestingSessionLocal


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_task(client: TestClient, token: str) -> str:
    response = client.post(
        "/tasks",
        headers=auth_headers(token),
        json={
            "title": "Mission task",
            "purpose": "inspection",
            "location": "Shenzhen Bay",
            "date": "2026-08-18",
            "start_time": "14:00",
            "end_time": "16:00",
            "task_type": "inspection",
        },
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def build_artifacts(payload: CruiseEvaluateRequest) -> CruiseEvaluationArtifacts:
    location = LocationInfo(
        location_id="loc-1",
        name=payload.location,
        latitude="22.5",
        longitude="113.9",
    )
    hourly_weather = [
        WeatherHourData(
            fx_time="2026-08-18T14:00:00+08:00",
            text="Sunny",
            wind_speed="8",
            wind_scale="1-2",
            precip="0",
            pop="0",
            humidity="55",
        ),
        WeatherHourData(
            fx_time="2026-08-18T15:00:00+08:00",
            text="Sunny",
            wind_speed="9",
            wind_scale="1-2",
            precip="0",
            pop="0",
            humidity="56",
        ),
    ]
    weather = WeatherDataBundle(location=location, update_time="2026-08-18T13:00:00+08:00", hourly_weather=hourly_weather)
    warnings = WarningDataBundle(warnings=[], has_warning=False, warning_count=0)
    advice = assess_cruise_window(hourly_weather, warnings, task_type=payload.task_type)
    response = CruiseAssessmentResponse(
        request={
            "location": payload.location,
            "date": payload.normalized_date,
            "start_time": payload.normalized_start_time,
            "end_time": payload.normalized_end_time,
            "task_type": payload.task_type,
            "purpose": payload.purpose,
            "spans_next_day": payload.spans_next_day,
            "start_datetime": payload.start_datetime,
            "end_datetime": payload.end_datetime,
        },
        weather=weather,
        warnings=warnings,
        advice=advice,
    )
    return CruiseEvaluationArtifacts(
        response=response,
        provider_name="qweather",
        raw_location_payload={"location": [{"id": "loc-1"}]},
        raw_hourly_weather_payload={"updateTime": "2026-08-18T13:00:00+08:00"},
        raw_warning_payload={"metadata": {"timestamp": "2026-08-18T13:00:00+08:00"}},
        standardized_location=location,
        standardized_weather=weather,
        standardized_warnings=warnings,
    )


def build_high_risk_artifacts(payload: CruiseEvaluateRequest) -> CruiseEvaluationArtifacts:
    location = LocationInfo(
        location_id="loc-1",
        name=payload.location,
        latitude="22.5",
        longitude="113.9",
    )
    hourly_weather = [
        WeatherHourData(
            fx_time=f"{payload.normalized_date}T{payload.normalized_start_time}:00+08:00",
            text="Sunny",
            wind_speed="30",
            wind_scale="5-6",
            precip="0",
            pop="0",
            humidity="55",
        )
    ]
    weather = WeatherDataBundle(location=location, update_time="2026-08-18T13:50:00+08:00", hourly_weather=hourly_weather)
    warnings = WarningDataBundle(warnings=[], has_warning=False, warning_count=0)
    advice = assess_cruise_window(hourly_weather, warnings, task_type=payload.task_type)
    response = CruiseAssessmentResponse(
        request={
            "location": payload.location,
            "date": payload.normalized_date,
            "start_time": payload.normalized_start_time,
            "end_time": payload.normalized_end_time,
            "task_type": payload.task_type,
            "purpose": payload.purpose,
            "spans_next_day": payload.spans_next_day,
            "start_datetime": payload.start_datetime,
            "end_datetime": payload.end_datetime,
        },
        weather=weather,
        warnings=warnings,
        advice=advice,
    )
    return CruiseEvaluationArtifacts(
        response=response,
        provider_name="qweather",
        raw_location_payload={"location": [{"id": "loc-1"}]},
        raw_hourly_weather_payload={"updateTime": "2026-08-18T13:50:00+08:00"},
        raw_warning_payload={"metadata": {"timestamp": "2026-08-18T13:50:00+08:00"}},
        standardized_location=location,
        standardized_weather=weather,
        standardized_warnings=warnings,
    )


def build_recommendation(payload: RecommendationRequest) -> RecommendationResponse:
    location = LocationInfo(location_id="loc-1", name=payload.location, latitude="22.5", longitude="113.9")
    weather = WeatherDataBundle(location=location, update_time="2026-08-18T13:00:00+08:00", hourly_weather=[])
    warnings = WarningDataBundle(warnings=[], has_warning=False, warning_count=0)
    return RecommendationResponse(
        request={
            "location": payload.location,
            "date": payload.date,
            "task_type": payload.task_type,
            "purpose": payload.purpose,
            "scan_hours": payload.scan_hours,
            "min_window_hours": payload.min_window_hours,
        },
        weather=weather,
        warnings=warnings,
        recommendation=RecommendationResult(
            strategy=RecommendationStrategy(min_window_hours=payload.min_window_hours, sort_rules=[]),
            recommended_windows=[
                RecommendationWindow(
                    rank=1,
                    start_time="2026-08-18T14:00:00+08:00",
                    end_time="2026-08-18T16:00:00+08:00",
                    duration_hours=2,
                    overall_decision=RiskDecision.SUITABLE,
                    risk_score=0,
                    reasons=["stable weather"],
                )
            ],
            total_candidates=1,
        ),
    )


@pytest.fixture
def task_history_tokens(api_session_factory: sessionmaker[Session]) -> dict[str, str]:
    with api_session_factory.begin() as db:
        db.add_all(
            [
                User(id="owner", username="owner", password_hash="UNUSABLE_PASSWORD", role="user"),
                User(id="other", username="other", password_hash="UNUSABLE_PASSWORD", role="user"),
                User(id="auditor", username="auditor", password_hash="UNUSABLE_PASSWORD", role="admin"),
            ]
        )
    return {user_id: create_access_token(user_id) for user_id in ("owner", "other", "auditor")}


def test_task_evaluation_readback_and_cancellation(
    api_client: TestClient,
    api_session_factory: sessionmaker[Session],
    task_history_tokens: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.history_query.SessionLocal", api_session_factory)
    evaluate = Mock(side_effect=build_artifacts)
    monkeypatch.setattr("app.services.mission_task_execution.evaluate_cruise_request_with_artifacts", evaluate)

    owner_token = task_history_tokens["owner"]
    other_token = task_history_tokens["other"]
    owner_headers = auth_headers(owner_token)
    other_headers = auth_headers(other_token)
    task_id = create_task(api_client, owner_token)
    other_task_id = create_task(api_client, other_token)
    task_url = f"/tasks/{task_id}"
    evaluate_url = f"{task_url}/evaluate"

    evaluation = api_client.post(evaluate_url, json=versioned_task_payload(api_client, task_id, owner_headers), headers=owner_headers)
    assert evaluation.status_code == 200
    result = evaluation.json()
    assert result["request"]["task_id"] == task_id
    request_id = result["request"]["request_id"]
    decision = result["advice"]["overall_decision"]

    task_detail = api_client.get(task_url, headers=owner_headers)
    assert task_detail.status_code == 200
    task = task_detail.json()
    assert task["status"] == "evaluated"
    assert task["latest_request_id"] == request_id
    assert task["latest_decision"] == decision
    assert task["request_ids"] == [request_id]

    history_url = f"/cruise/history/{request_id}"
    history_response = api_client.get(history_url, headers=owner_headers)
    assert history_response.status_code == 200
    history = history_response.json()
    assert history["request_id"] == request_id
    assert history["advice"]["overall_decision"] == decision

    other_tasks = api_client.get("/tasks", headers=other_headers)
    assert other_tasks.status_code == 200
    assert [item["id"] for item in other_tasks.json()["items"]] == [other_task_id]
    assert api_client.get(task_url, headers=other_headers).status_code == 404
    assert api_client.post(evaluate_url, json=versioned_task_payload(api_client, task_id, other_headers), headers=other_headers).status_code == 403

    cancelled = api_client.patch(f"{task_url}/status", headers=owner_headers, json=versioned_task_payload(api_client, task_id, owner_headers, {"status": "cancelled"}))
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert api_client.post(evaluate_url, json=versioned_task_payload(api_client, task_id, owner_headers), headers=owner_headers).status_code == 409
    evaluate.assert_called_once()

    cancelled_detail = api_client.get(task_url, headers=owner_headers)
    assert cancelled_detail.status_code == 200
    cancelled_task = cancelled_detail.json()
    assert cancelled_task["status"] == "cancelled"
    assert cancelled_task["latest_request_id"] == request_id
    assert cancelled_task["latest_decision"] == decision
    assert cancelled_task["request_ids"] == [request_id]

    saved_history = api_client.get(history_url, headers=owner_headers)
    assert saved_history.status_code == 200
    assert saved_history.json() == history

    with api_session_factory() as db:
        requests = db.scalars(select(TaskRequest.request_id).where(TaskRequest.task_id == task_id)).all()
        assessments = db.scalars(select(CruiseAssessment.request_id).where(CruiseAssessment.task_id == task_id)).all()
        assert requests == [request_id]
        assert assessments == [request_id]


@pytest.mark.parametrize("task_link", ["both", "request_only", "assessment_only"])
def test_task_evaluation_history_requires_task_visibility(
    api_client: TestClient,
    api_session_factory: sessionmaker[Session],
    task_history_tokens: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    task_link: str,
) -> None:
    monkeypatch.setattr("app.services.history_query.SessionLocal", api_session_factory)
    owner_token = task_history_tokens["owner"]
    task_id = create_task(api_client, owner_token)
    with patch("app.services.mission_task_execution.evaluate_cruise_request_with_artifacts", side_effect=build_artifacts):
        evaluation = api_client.post(f"/tasks/{task_id}/evaluate", json=versioned_task_payload(api_client, task_id, auth_headers(owner_token)), headers=auth_headers(owner_token))
    assert evaluation.status_code == 200
    result = evaluation.json()
    request_id = result["request"]["request_id"]

    with api_session_factory.begin() as db:
        if task_link == "request_only":
            db.execute(update(CruiseAssessment).where(CruiseAssessment.request_id == request_id).values(task_id=None))
        if task_link == "assessment_only":
            db.execute(update(TaskRequest).where(TaskRequest.request_id == request_id).values(task_id=None))

    other_headers = auth_headers(task_history_tokens["other"])
    admin_headers = auth_headers(task_history_tokens["auditor"])
    history_url = f"/cruise/history/{request_id}"
    for url in (history_url, f"{history_url}/composed"):
        assert api_client.get(url, headers=other_headers).status_code == 404
        assert api_client.get(url).status_code == 401
        assert api_client.get(url, headers=admin_headers).status_code == 200

    history = api_client.get(history_url, headers=auth_headers(owner_token))
    assert history.status_code == 200
    assert history.json()["request_id"] == request_id
    assert history.json()["advice"]["overall_decision"] == result["advice"]["overall_decision"]

    composed_history = api_client.get(f"{history_url}/composed", headers=auth_headers(owner_token))
    assert composed_history.status_code == 200
    assert composed_history.json()["history_summary"]["request_id"] == request_id


def test_task_recommend_and_select_window_updates_schedule() -> None:
    client, tokens, SessionLocal = build_test_client()
    try:
        task_id = create_task(client, tokens["user-a"])

        with patch("app.services.mission_task_execution.build_recommendation_response", side_effect=build_recommendation):
            recommend_response = client.post(
                f"/tasks/{task_id}/recommend",
                headers=auth_headers(tokens["user-a"]),
                json=versioned_task_payload(client, task_id, auth_headers(tokens["user-a"]), {"scan_hours": 24, "min_window_hours": 2}),
            )

        assert recommend_response.status_code == 200
        assert recommend_response.json()["request"]["task_id"] == task_id
        assert recommend_response.json()["recommendation"]["recommended_windows"][0]["rank"] == 1

        select_response = client.post(
            f"/tasks/{task_id}/select-window",
            headers=auth_headers(tokens["user-a"]),
            json=versioned_task_payload(client, task_id, auth_headers(tokens["user-a"]), {"rank": 1}),
        )
        assert select_response.status_code == 200
        selected = select_response.json()
        assert selected["status"] == "scheduled"
        assert selected["selected_window"]["rank"] == 1

        with SessionLocal() as db:
            task = db.get(MissionTask, task_id)
            assert task is not None
            assert task.selected_window_json["rank"] == 1
            assert "latest_recommendation" in task.metadata_json
    finally:
        app.dependency_overrides.clear()


def test_task_operations_reject_missing_fields_and_other_users() -> None:
    client, tokens, _ = build_test_client()
    try:
        create_response = client.post(
            "/tasks",
            headers=auth_headers(tokens["user-a"]),
            json={"title": "Incomplete task"},
        )
        task_id = create_response.json()["id"]

        missing_response = client.post(f"/tasks/{task_id}/evaluate", json=versioned_task_payload(client, task_id, auth_headers(tokens["user-a"])), headers=auth_headers(tokens["user-a"]))
        assert missing_response.status_code == 422
        assert "location" in missing_response.json()["detail"]["missing_fields"]

        other_user_response = client.post(f"/tasks/{task_id}/recommend", json=versioned_task_payload(client, task_id, auth_headers(tokens["user-b"])), headers=auth_headers(tokens["user-b"]))
        assert other_user_response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_preflight_check_creates_new_snapshot_and_overrides_latest_decision() -> None:
    client, tokens, SessionLocal = build_test_client()
    try:
        task_id = create_task(client, tokens["user-a"])
        with patch("app.services.mission_task_execution.build_recommendation_response", side_effect=build_recommendation):
            assert client.post(
                f"/tasks/{task_id}/recommend",
                headers=auth_headers(tokens["user-a"]),
                json=versioned_task_payload(client, task_id, auth_headers(tokens["user-a"]), {"scan_hours": 24, "min_window_hours": 2}),
            ).status_code == 200
        assert client.post(
            f"/tasks/{task_id}/select-window",
            headers=auth_headers(tokens["user-a"]),
            json=versioned_task_payload(client, task_id, auth_headers(tokens["user-a"]), {"rank": 1}),
        ).status_code == 200

        with patch("app.services.mission_task_execution.evaluate_cruise_request_with_artifacts", side_effect=build_high_risk_artifacts):
            response = client.post(f"/tasks/{task_id}/preflight-check", json=versioned_task_payload(client, task_id, auth_headers(tokens["user-a"])), headers=auth_headers(tokens["user-a"]))

        assert response.status_code == 200
        payload = response.json()
        assert payload["request"]["task_id"] == task_id
        assert payload["request"]["request_type"] == "preflight_check"
        assert payload["request"]["start_time"] == "14:00"
        assert payload["request"]["end_time"] == "16:00"
        request_id = payload["request"]["request_id"]

        with SessionLocal() as db:
            task = db.get(MissionTask, task_id)
            assert task is not None
            assert task.status == "recheck"
            assert task.latest_request_id == request_id
            assert task.latest_trace_id is not None
            assert task.latest_decision == payload["advice"]["overall_decision"]
            assert task.selected_window_json["rank"] == 1
            assert task.metadata_json["latest_preflight_check"]["request_id"] == request_id
            assert task.metadata_json["latest_preflight_check"]["trace_id"] == task.latest_trace_id

            task_request = db.scalar(select(TaskRequest).where(TaskRequest.request_id == request_id))
            assessment = db.scalar(select(CruiseAssessment).where(CruiseAssessment.request_id == request_id))
            assert task_request is not None
            assert task_request.task_id == task_id
            assert task_request.request_type == "preflight_check"
            assert assessment is not None
            assert assessment.task_id == task_id
            trace_events = list(
                db.scalars(select(AgentTraceEventRecord).where(AgentTraceEventRecord.trace_id == task.latest_trace_id))
            )
            assert len(trace_events) == 3
            assert {event.task_id for event in trace_events} == {task_id}
    finally:
        app.dependency_overrides.clear()


def test_preflight_check_rejects_cancelled_task() -> None:
    client, tokens, _ = build_test_client()
    try:
        task_id = create_task(client, tokens["user-a"])
        cancel_response = client.patch(
            f"/tasks/{task_id}/status",
            headers=auth_headers(tokens["user-a"]),
            json=versioned_task_payload(client, task_id, auth_headers(tokens["user-a"]), {"status": "cancelled"}),
        )
        assert cancel_response.status_code == 200

        response = client.post(f"/tasks/{task_id}/preflight-check", json=versioned_task_payload(client, task_id, auth_headers(tokens["user-a"])), headers=auth_headers(tokens["user-a"]))
        assert response.status_code == 409
    finally:
        app.dependency_overrides.clear()
