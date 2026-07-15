from fastapi import HTTPException

from app.db.models import (
    CruiseAssessment,
    CruiseHourlyAssessment,
    Location,
    TaskRequest,
    WeatherHourlySnapshot,
    WeatherWarningSnapshot,
)
from app.db.session import SessionLocal
from app.schemas import (
    CruiseAssessmentAdvice,
    CruiseHistoryResponse,
    HourlyAssessment,
    LocationInfo,
    WarningData,
    WarningDataBundle,
    WeatherDataBundle,
    WeatherHourData,
)


def get_cruise_history(request_id: str) -> CruiseHistoryResponse:
    with SessionLocal() as session:
        task_request = session.query(TaskRequest).filter(TaskRequest.request_id == request_id).one_or_none()
        if task_request is None:
            raise HTTPException(status_code=404, detail=f"history not found for request_id={request_id}")

        assessment = session.query(CruiseAssessment).filter(CruiseAssessment.request_id == request_id).one_or_none()
        if assessment is None:
            raise HTTPException(status_code=404, detail=f"assessment not found for request_id={request_id}")

        location = session.query(Location).filter(Location.id == assessment.location_id).one()
        hourly_assessments = (
            session.query(CruiseHourlyAssessment)
            .filter(CruiseHourlyAssessment.assessment_id == assessment.id)
            .order_by(CruiseHourlyAssessment.fx_time.asc())
            .all()
        )
        warning_snapshots = (
            session.query(WeatherWarningSnapshot)
            .filter(
                WeatherWarningSnapshot.request_id == request_id,
                WeatherWarningSnapshot.location_id == location.id,
            )
            .order_by(WeatherWarningSnapshot.publish_time.asc())
            .all()
        )

        weather_snapshot_ids = [item.weather_snapshot_id for item in hourly_assessments if item.weather_snapshot_id]
        weather_snapshots = []
        if weather_snapshot_ids:
            weather_snapshots = (
                session.query(WeatherHourlySnapshot)
                .filter(WeatherHourlySnapshot.id.in_(weather_snapshot_ids))
                .order_by(WeatherHourlySnapshot.fx_time.asc())
                .all()
            )

        weather_by_id = {item.id: item for item in weather_snapshots}
        weather_bundle = WeatherDataBundle(
            location=LocationInfo(
                location_id=location.provider_location_id,
                name=location.name,
                latitude=location.latitude,
                longitude=location.longitude,
                adm1=location.adm1,
                adm2=location.adm2,
                country=location.country,
                timezone=location.timezone,
                utc_offset=location.utc_offset,
            ),
            update_time=weather_snapshots[0].update_time if weather_snapshots else None,
            hourly_weather=[
                WeatherHourData(
                    fx_time=item.fx_time,
                    temp=item.temp,
                    text=item.text,
                    wind_scale=item.wind_scale,
                    wind_speed=item.wind_speed,
                    humidity=item.humidity,
                    precip=item.precip,
                    pop=item.pop,
                    pressure=item.pressure,
                    cloud=item.cloud,
                )
                for item in weather_snapshots
            ],
        )
        warning_bundle = WarningDataBundle(
            warnings=[
                WarningData(
                    warning_id=item.warning_id,
                    event_type=item.event_type,
                    warning_level=item.warning_level,
                    title=item.title,
                    sender=item.sender,
                    publish_time=item.publish_time,
                    start_time=item.start_time,
                    end_time=item.end_time,
                    status=item.status,
                    text=item.text,
                )
                for item in warning_snapshots
            ],
            has_warning=bool(warning_snapshots),
            warning_count=len(warning_snapshots),
        )
        advice = CruiseAssessmentAdvice(
            allow_cruise=assessment.allow_cruise,
            overall_decision=assessment.overall_decision,
            summary_risk_factors=list(assessment.summary_risk_factors_json or []),
            hourly_assessment=[
                HourlyAssessment(
                    fx_time=item.fx_time,
                    decision=item.decision,
                    risk_factors=list(item.risk_factors_json or []),
                    weather=_build_hourly_weather_dict(weather_by_id.get(item.weather_snapshot_id)),
                )
                for item in hourly_assessments
            ],
        )

        return CruiseHistoryResponse(
            request_id=request_id,
            created_at=task_request.created_at.isoformat(),
            request=task_request.raw_request_json,
            weather=weather_bundle,
            warnings=warning_bundle,
            advice=advice,
        )


def _build_hourly_weather_dict(snapshot: WeatherHourlySnapshot | None) -> dict[str, str | None]:
    if snapshot is None:
        return {}
    return {
        "fx_time": snapshot.fx_time,
        "temp": snapshot.temp,
        "text": snapshot.text,
        "wind_scale": snapshot.wind_scale,
        "wind_speed": snapshot.wind_speed,
        "humidity": snapshot.humidity,
        "precip": snapshot.precip,
        "pop": snapshot.pop,
        "pressure": snapshot.pressure,
        "cloud": snapshot.cloud,
    }
