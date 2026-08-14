from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.rules import assess_cruise_window
from app.schemas import (
    CruiseAssessmentResponse,
    CruiseEvaluateRequest,
    LocationInfo,
    WarningDataBundle,
    WeatherDataBundle,
    WeatherHourData,
)
from app.services.cruise_evaluator import CruiseEvaluationArtifacts
from app.services.history_persistence import _persist_cruise_evaluation
import app.services.history_query as history_query


def build_session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def test_history_detail_returns_rule_snapshot_and_rule_hits(monkeypatch) -> None:
    SessionLocal = build_session_factory()
    monkeypatch.setattr(history_query, "SessionLocal", SessionLocal)

    payload = CruiseEvaluateRequest(
        location="深圳湾",
        date="2026-08-14",
        start_time="08:00",
        end_time="09:00",
        task_type="cruise",
    )
    hourly_weather = [
        WeatherHourData(
            fx_time="2026-08-14T08:00:00+08:00",
            text="晴",
            wind_speed="25",
            wind_scale="1-2",
            precip="0",
            pop="10",
            humidity="60",
        )
    ]
    location = LocationInfo(
        location_id="101280601",
        name="深圳",
        latitude="22.543",
        longitude="114.057",
    )
    weather_bundle = WeatherDataBundle(location=location, update_time="2026-08-14T07:00:00+08:00", hourly_weather=hourly_weather)
    warnings = WarningDataBundle(warnings=[], has_warning=False, warning_count=0)
    advice = assess_cruise_window(hourly_weather, warnings, task_type="cruise")
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
        weather=weather_bundle,
        warnings=warnings,
        advice=advice,
    )
    artifacts = CruiseEvaluationArtifacts(
        response=response,
        provider_name="qweather",
        raw_location_payload={"location": []},
        raw_hourly_weather_payload={"updateTime": "2026-08-14T07:00:00+08:00"},
        raw_warning_payload={"metadata": {"timestamp": "2026-08-14T07:00:00+08:00"}},
        standardized_location=location,
        standardized_weather=weather_bundle,
        standardized_warnings=warnings,
    )

    with SessionLocal() as db:
        _persist_cruise_evaluation(session=db, request_id="history-rule-1", payload=payload, artifacts=artifacts)
        db.commit()

    history = history_query.get_cruise_history("history-rule-1")

    assert history.advice.rule_set_id == "system_default:cruise"
    assert history.advice.rule_set_version == 1
    assert history.advice.rule_snapshot["task_type"] == "cruise"
    assert history.advice.rule_snapshot["hourly"]["prohibited_wind_speed_kmh"] == 25
    assert history.advice.rule_hits[0].metric == "wind_speed"
    assert history.advice.rule_hits[0].actual_value == 25
    assert history.advice.hourly_assessment[0].rule_hits[0].label == "风速偏高"
