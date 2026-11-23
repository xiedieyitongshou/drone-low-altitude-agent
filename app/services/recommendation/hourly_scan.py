from datetime import date

from app.schemas.assessment import CruiseAssessmentAdvice
from app.schemas.recommendation import RecommendationResult
from app.schemas.request import CruiseEvaluateRequest
from app.schemas.warning import WarningDataBundle
from app.schemas.weather import WeatherDataBundle
from app.rules import assess_cruise_window
from app.services.recommendation.window_recommender import RecommendationConfig, build_recommendation_result
from app.services.weather.exceptions import WeatherDataError
from app.services.weather.validation import forecast_datetime, weather_datetime


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
    if not filtered_weather and weather_data.hourly_weather:
        raise WeatherDataError(
            "当前预报未覆盖所选日期，无法推荐执行窗口，请调整日期。",
            error_code="WEATHER_FORECAST_OUT_OF_RANGE", retryable=False,
        )
    if len(filtered_weather) < min_window_hours:
        raise WeatherDataError("可用天气数据不足以覆盖所需的连续窗口，无法完成推荐。")
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
    filtered = sorted([
        hour
        for hour in weather_data.hourly_weather
        if forecast_datetime(hour.fx_time).date() >= start_date
    ], key=lambda hour: weather_datetime(hour.fx_time))
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
