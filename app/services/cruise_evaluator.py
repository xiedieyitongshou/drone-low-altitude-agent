from contextlib import suppress

from app.rules import assess_cruise_window
from app.schemas import CruiseAssessmentResponse, CruiseEvaluateRequest
from app.services.weather import QWeatherService, extract_hourly_weather_from_request, to_warning_data_bundle, to_weather_data_bundle


def evaluate_cruise_request(payload: CruiseEvaluateRequest) -> CruiseAssessmentResponse:
    weather_service = QWeatherService()
    try:
        locations = weather_service.lookup_location(payload.location, number=1)
        selected_location = locations[0]

        hourly_response = weather_service.get_hourly_weather(selected_location.location_id, hours="72h")
        warning_response = weather_service.get_weather_warning(
            latitude=selected_location.latitude,
            longitude=selected_location.longitude,
        )

        standardized_weather = to_weather_data_bundle(selected_location, hourly_response)
        standardized_warnings = to_warning_data_bundle(warning_response)
        target_hourly_weather = extract_hourly_weather_from_request(payload, standardized_weather)
        target_weather_bundle = standardized_weather.model_copy(
            update={"hourly_weather": target_hourly_weather}
        )
        advice = assess_cruise_window(
            target_hourly_weather,
            standardized_warnings,
            task_type=payload.task_type,
        )

        return CruiseAssessmentResponse(
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
    finally:
        with suppress(Exception):
            weather_service.close()


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
