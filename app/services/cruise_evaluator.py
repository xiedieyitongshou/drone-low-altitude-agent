from contextlib import suppress
from dataclasses import dataclass

from app.rules import assess_cruise_window
from app.schemas import CruiseAssessmentResponse, CruiseEvaluateRequest
from app.schemas.warning import WarningDataBundle
from app.schemas.weather import LocationInfo, WeatherDataBundle
from app.services.weather import (
    LocationNotFoundError,
    QWeatherService,
    extract_hourly_weather_from_request,
    to_warning_data_bundle,
    to_weather_data_bundle,
)
from app.services.weather.schemas import GeoLocation, HourlyWeatherResponse, WeatherWarningResponse


@dataclass
class CruiseEvaluationArtifacts:
    response: CruiseAssessmentResponse
    provider_name: str
    raw_location_payload: dict
    raw_hourly_weather_payload: dict
    raw_warning_payload: dict
    standardized_location: LocationInfo
    standardized_weather: WeatherDataBundle
    standardized_warnings: WarningDataBundle


def evaluate_cruise_request_with_artifacts(payload: CruiseEvaluateRequest) -> CruiseEvaluationArtifacts:
    weather_service = QWeatherService()
    try:
        raw_location_payload = weather_service.lookup_location_payload(payload.location, number=1)
        locations = [GeoLocation.model_validate(item) for item in raw_location_payload.get("location", [])]
        if not locations:
            raise LocationNotFoundError(f"No matching location found for: {payload.location}")
        selected_location = locations[0]

        raw_hourly_weather_payload = weather_service.get_hourly_weather_payload(selected_location.location_id, hours="72h")
        hourly_response = HourlyWeatherResponse.model_validate(raw_hourly_weather_payload)
        raw_warning_payload = weather_service.get_weather_warning_payload(
            latitude=selected_location.latitude,
            longitude=selected_location.longitude,
        )
        warning_response = WeatherWarningResponse.model_validate(raw_warning_payload)

        standardized_weather = to_weather_data_bundle(selected_location, hourly_response)
        standardized_warnings = to_warning_data_bundle(warning_response)
        standardized_location = standardized_weather.location
        target_hourly_weather = extract_hourly_weather_from_request(payload, standardized_weather)
        target_weather_bundle = standardized_weather.model_copy(
            update={"hourly_weather": target_hourly_weather}
        )
        advice = assess_cruise_window(
            target_hourly_weather,
            standardized_warnings,
            task_type=payload.task_type,
        )

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
            weather=target_weather_bundle,
            warnings=standardized_warnings,
            advice=advice,
        )

        return CruiseEvaluationArtifacts(
            response=response,
            provider_name="qweather",
            raw_location_payload=raw_location_payload,
            raw_hourly_weather_payload=raw_hourly_weather_payload,
            raw_warning_payload=raw_warning_payload,
            standardized_location=standardized_location,
            standardized_weather=standardized_weather,
            standardized_warnings=standardized_warnings,
        )
    finally:
        with suppress(Exception):
            weather_service.close()


def evaluate_cruise_request(payload: CruiseEvaluateRequest) -> CruiseAssessmentResponse:
    return evaluate_cruise_request_with_artifacts(payload).response


def build_cruise_request(
    *,
    location: str,
    date: str,
    start_time: str,
    end_time: str,
    task_type: str,
    purpose: str | None,
) -> CruiseEvaluateRequest:
    return CruiseEvaluateRequest(
        location=location,
        date=date,
        start_time=start_time,
        end_time=end_time,
        task_type=task_type,
        purpose=purpose,
    )
