from contextlib import suppress

from app.schemas import RecommendationRequest, RecommendationResponse
from app.services.recommendation import build_recommendation_from_weather, build_recommendation_request_preview
from app.services.weather import QWeatherService, to_warning_data_bundle, to_weather_data_bundle


def build_recommendation_response(payload: RecommendationRequest) -> RecommendationResponse:
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
        filtered_weather, _, recommendation = build_recommendation_from_weather(
            location=payload.location,
            date_text=payload.date,
            task_type=payload.task_type,
            weather_data=standardized_weather,
            warnings=standardized_warnings,
            scan_hours=payload.scan_hours,
            min_window_hours=payload.min_window_hours,
        )
        target_weather_bundle = standardized_weather.model_copy(update={"hourly_weather": filtered_weather})

        return RecommendationResponse(
            request=build_recommendation_request_preview(
                location=payload.location,
                date_text=payload.date,
                task_type=payload.task_type,
                purpose=payload.purpose,
                scan_hours=payload.scan_hours,
                min_window_hours=payload.min_window_hours,
            ),
            weather=target_weather_bundle,
            warnings=standardized_warnings,
            recommendation=recommendation,
        )
    finally:
        with suppress(Exception):
            weather_service.close()
