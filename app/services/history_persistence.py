from uuid import uuid4

from sqlalchemy.orm import Session

from app.rules.mission_profiles import build_system_rule_snapshot as _build_system_rule_snapshot
from app.db.models import (
    CruiseAssessment,
    CruiseHourlyAssessment,
    Location,
    TaskRequest,
    WeatherHourlySnapshot,
    WeatherProviderSnapshot,
    WeatherWarningSnapshot,
)
from app.db.session import SessionLocal
from app.services.cruise_evaluator import CruiseEvaluationArtifacts
from app.services.run_observability import current_observation, timed_stage


@timed_stage("history_write")
def persist_cruise_evaluation(
    *,
    payload,
    artifacts: CruiseEvaluationArtifacts,
    task_id: str | None = None,
    request_type: str = "evaluate",
    user_id: str | None = None,
    trace_id: str | None = None,
    db: Session | None = None,
) -> str:
    request_id = uuid4().hex
    if db is not None:
        try:
            _persist_cruise_evaluation(
                session=db, request_id=request_id, payload=payload, artifacts=artifacts,
                task_id=task_id, request_type=request_type, user_id=user_id, trace_id=trace_id,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        return request_id
    with SessionLocal() as session:
        _persist_cruise_evaluation(
            session=session,
            request_id=request_id,
            payload=payload,
            artifacts=artifacts,
            task_id=task_id,
            request_type=request_type,
            user_id=user_id,
            trace_id=trace_id,
        )
        session.commit()
    return request_id


def _persist_cruise_evaluation(
    *,
    session: Session,
    request_id: str,
    payload,
    artifacts: CruiseEvaluationArtifacts,
    task_id: str | None = None,
    request_type: str = "evaluate",
    user_id: str | None = None,
    trace_id: str | None = None,
) -> None:
    observation = current_observation()
    user_id = user_id or (observation.user_id if observation else None)
    trace_id = trace_id or (observation.trace_id if observation else None)
    raw_request = payload.model_dump()
    if trace_id:
        raw_request["trace_id"] = trace_id
    task_request = TaskRequest(
        request_id=request_id,
        user_id=user_id,
        trace_id=trace_id,
        task_id=task_id,
        request_type=request_type,
        location_text=payload.location,
        task_date=payload.normalized_date,
        start_time=payload.normalized_start_time,
        end_time=payload.normalized_end_time,
        task_type=payload.task_type,
        purpose=payload.purpose,
        raw_request_json=raw_request,
    )
    session.add(task_request)

    location = _get_or_create_location(session=session, artifacts=artifacts)
    session.flush()

    location_snapshot = WeatherProviderSnapshot(
        request_id=request_id,
        location_id=location.id,
        provider_name=artifacts.provider_name,
        snapshot_type="geo",
        provider_endpoint="/geo/v2/city/lookup",
        provider_update_time=None,
        raw_payload_json=artifacts.raw_location_payload,
    )
    hourly_provider_snapshot = WeatherProviderSnapshot(
        request_id=request_id,
        location_id=location.id,
        provider_name=artifacts.provider_name,
        snapshot_type="hourly_weather",
        provider_endpoint="/v7/weather/72h",
        provider_update_time=artifacts.raw_hourly_weather_payload.get("updateTime"),
        raw_payload_json=artifacts.raw_hourly_weather_payload,
    )
    warning_provider_snapshot = WeatherProviderSnapshot(
        request_id=request_id,
        location_id=location.id,
        provider_name=artifacts.provider_name,
        snapshot_type="warning",
        provider_endpoint="/weatheralert/v1/current/{latitude}/{longitude}",
        provider_update_time=artifacts.raw_warning_payload.get("metadata", {}).get("timestamp"),
        raw_payload_json=artifacts.raw_warning_payload,
    )
    session.add_all([location_snapshot, hourly_provider_snapshot, warning_provider_snapshot])
    session.flush()

    weather_snapshot_by_fx_time: dict[str, int] = {}
    for hour in artifacts.standardized_weather.hourly_weather:
        weather_snapshot = WeatherHourlySnapshot(
            request_id=request_id,
            location_id=location.id,
            provider_snapshot_id=hourly_provider_snapshot.id,
            update_time=artifacts.standardized_weather.update_time,
            fx_time=hour.fx_time,
            temp=hour.temp,
            text=hour.text,
            wind_scale=hour.wind_scale,
            wind_speed=hour.wind_speed,
            humidity=hour.humidity,
            precip=hour.precip,
            pop=hour.pop,
            pressure=hour.pressure,
            cloud=hour.cloud,
        )
        session.add(weather_snapshot)
        session.flush()
        weather_snapshot_by_fx_time[hour.fx_time] = weather_snapshot.id

    for warning in artifacts.standardized_warnings.warnings:
        session.add(
            WeatherWarningSnapshot(
                request_id=request_id,
                location_id=location.id,
                provider_snapshot_id=warning_provider_snapshot.id,
                warning_id=warning.warning_id,
                event_type=warning.event_type,
                warning_level=warning.warning_level,
                title=warning.title,
                sender=warning.sender,
                publish_time=warning.publish_time,
                start_time=warning.start_time,
                end_time=warning.end_time,
                status=warning.status,
                text=warning.text,
            )
        )

    rule_snapshot = artifacts.response.advice.rule_snapshot or _build_system_rule_snapshot(payload.task_type)
    rule_set_id = artifacts.response.advice.rule_set_id or getattr(payload, "rule_set_id", None) or str(rule_snapshot["rule_set_id"])
    rule_set_version = artifacts.response.advice.rule_set_version or getattr(payload, "rule_set_version", None) or int(rule_snapshot["rule_set_version"])

    assessment = CruiseAssessment(
        request_id=request_id,
        task_id=task_id,
        location_id=location.id,
        allow_cruise=artifacts.response.advice.allow_cruise,
        overall_decision=artifacts.response.advice.overall_decision,
        summary_risk_factors_json=list(artifacts.response.advice.summary_risk_factors),
        rule_set_id=rule_set_id,
        rule_set_version=rule_set_version,
        rule_snapshot_json=rule_snapshot,
        rule_hits_json=[hit.model_dump(mode="json") for hit in artifacts.response.advice.rule_hits],
    )
    session.add(assessment)
    session.flush()

    for item in artifacts.response.advice.hourly_assessment:
        session.add(
            CruiseHourlyAssessment(
                assessment_id=assessment.id,
                fx_time=item.fx_time,
                decision=item.decision,
                risk_factors_json=list(item.risk_factors),
                rule_hits_json=[hit.model_dump(mode="json") for hit in item.rule_hits],
                weather_snapshot_id=weather_snapshot_by_fx_time.get(item.fx_time),
            )
        )


def _get_or_create_location(*, session: Session, artifacts: CruiseEvaluationArtifacts) -> Location:
    location = (
        session.query(Location)
        .filter(
            Location.provider_name == artifacts.provider_name,
            Location.provider_location_id == artifacts.standardized_location.location_id,
        )
        .one_or_none()
    )
    if location:
        return location

    location = Location(
        provider_name=artifacts.provider_name,
        provider_location_id=artifacts.standardized_location.location_id,
        name=artifacts.standardized_location.name,
        latitude=artifacts.standardized_location.latitude,
        longitude=artifacts.standardized_location.longitude,
        adm1=artifacts.standardized_location.adm1,
        adm2=artifacts.standardized_location.adm2,
        country=artifacts.standardized_location.country,
        timezone=artifacts.standardized_location.timezone,
        utc_offset=artifacts.standardized_location.utc_offset,
    )
    session.add(location)
    session.flush()
    return location
