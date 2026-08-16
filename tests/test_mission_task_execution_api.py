from collections.abc import Generator
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
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


def test_task_evaluate_persists_history_and_updates_task_status() -> None:
    client, tokens, SessionLocal = build_test_client()
    try:
        task_id = create_task(client, tokens["user-a"])
        with patch("app.services.mission_task_execution.evaluate_cruise_request_with_artifacts", side_effect=build_artifacts):
            response = client.post(f"/tasks/{task_id}/evaluate", headers=auth_headers(tokens["user-a"]))

        assert response.status_code == 200
        payload = response.json()
        assert payload["request"]["task_id"] == task_id
        request_id = payload["request"]["request_id"]

        with SessionLocal() as db:
            task = db.get(MissionTask, task_id)
            assert task is not None
            assert task.status == "evaluated"
            assert task.latest_request_id == request_id
            assert task.latest_decision == payload["advice"]["overall_decision"]
            task_request = db.scalar(select(TaskRequest).where(TaskRequest.request_id == request_id))
            assessment = db.scalar(select(CruiseAssessment).where(CruiseAssessment.request_id == request_id))
            assert task_request is not None
            assert task_request.task_id == task_id
            assert assessment is not None
            assert assessment.task_id == task_id
    finally:
        app.dependency_overrides.clear()


def test_task_recommend_and_select_window_updates_schedule() -> None:
    client, tokens, SessionLocal = build_test_client()
    try:
        task_id = create_task(client, tokens["user-a"])

        with patch("app.services.mission_task_execution.build_recommendation_response", side_effect=build_recommendation):
            recommend_response = client.post(
                f"/tasks/{task_id}/recommend",
                headers=auth_headers(tokens["user-a"]),
                json={"scan_hours": 24, "min_window_hours": 2},
            )

        assert recommend_response.status_code == 200
        assert recommend_response.json()["request"]["task_id"] == task_id
        assert recommend_response.json()["recommendation"]["recommended_windows"][0]["rank"] == 1

        select_response = client.post(
            f"/tasks/{task_id}/select-window",
            headers=auth_headers(tokens["user-a"]),
            json={"rank": 1},
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

        missing_response = client.post(f"/tasks/{task_id}/evaluate", headers=auth_headers(tokens["user-a"]))
        assert missing_response.status_code == 422
        assert "location" in missing_response.json()["detail"]["missing_fields"]

        other_user_response = client.post(f"/tasks/{task_id}/recommend", headers=auth_headers(tokens["user-b"]))
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
                json={"scan_hours": 24, "min_window_hours": 2},
            ).status_code == 200
        assert client.post(
            f"/tasks/{task_id}/select-window",
            headers=auth_headers(tokens["user-a"]),
            json={"rank": 1},
        ).status_code == 200

        with patch("app.services.mission_task_execution.evaluate_cruise_request_with_artifacts", side_effect=build_high_risk_artifacts):
            response = client.post(f"/tasks/{task_id}/preflight-check", headers=auth_headers(tokens["user-a"]))

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
            json={"status": "cancelled"},
        )
        assert cancel_response.status_code == 200

        response = client.post(f"/tasks/{task_id}/preflight-check", headers=auth_headers(tokens["user-a"]))
        assert response.status_code == 409
    finally:
        app.dependency_overrides.clear()
