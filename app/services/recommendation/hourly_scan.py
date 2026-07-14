from datetime import date, datetime

from app.schemas.assessment import CruiseAssessmentAdvice
from app.schemas.recommendation import RecommendationResult
from app.schemas.request import CruiseEvaluateRequest
from app.schemas.warning import WarningDataBundle
from app.schemas.weather import WeatherDataBundle
from app.rules import assess_cruise_window
from app.services.recommendation.window_recommender import RecommendationConfig, build_recommendation_result


def build_recommendation_from_weather(
    *,
    location: str,
    date_text: str,
    task_type: str,
    weather_data: WeatherDataBundle,
    warnings: WarningDataBundle,
    scan_hours: int = 72,
    min_window_hours: int = 2,
) -> tuple[list, CruiseAssessmentAdvice, RecommendationResult]:
    filtered_weather = filter_weather_from_date(
        weather_data=weather_data,
        start_date_text=date_text,
        max_hours=scan_hours,
    )
    advice = assess_cruise_window(
        filtered_weather,
        warnings,
        task_type=task_type,
    )
    recommendation = build_recommendation_result(
        advice.hourly_assessment,
        RecommendationConfig(
            min_window_hours=min_window_hours,
        ),
    )
    return filtered_weather, advice, recommendation


def filter_weather_from_date(
    *,
    weather_data: WeatherDataBundle,
    start_date_text: str,
    max_hours: int,
) -> list:
    start_date = date.fromisoformat(start_date_text)
    filtered = [
        hour
        for hour in weather_data.hourly_weather
        if datetime.fromisoformat(hour.fx_time).date() >= start_date
    ]
    if max_hours <= 0:
        return filtered
    return filtered[:max_hours]


def build_recommendation_request_preview(
    *,
    location: str,
    date_text: str,
    task_type: str,
    purpose: str | None,
    scan_hours: int,
    min_window_hours: int,
) -> dict[str, str | int | None]:
    request = CruiseEvaluateRequest(
        location=location,
        date=date_text,
        start_time="00:00",
        end_time="24:00",
        task_type=task_type,
        purpose=purpose,
    )
    return {
        "location": request.location,
        "date": request.normalized_date,
        "task_type": request.task_type,
        "purpose": request.purpose,
        "scan_hours": scan_hours,
        "min_window_hours": min_window_hours,
    }
