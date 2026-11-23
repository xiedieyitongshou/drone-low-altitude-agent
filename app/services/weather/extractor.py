from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.schemas.request import CruiseEvaluateRequest
from app.schemas.weather import WeatherDataBundle, WeatherHourData
from app.services.weather.exceptions import WeatherDataError
from app.services.weather.validation import forecast_datetime, weather_datetime, validate_window_coverage
from app.utils.timezone import APP_TIMEZONE


@dataclass(frozen=True)
class TimeWindow:
    start_datetime: datetime
    end_datetime: datetime


def parse_time_window(
    *,
    date_text: str,
    start_time_text: str,
    end_time_text: str,
) -> TimeWindow:
    request = CruiseEvaluateRequest(
        location="time-window-only",
        date=date_text,
        start_time=start_time_text,
        end_time=end_time_text,
        task_type="cruise",
    )
    return TimeWindow(
        start_datetime=datetime.fromisoformat(request.start_datetime),
        end_datetime=datetime.fromisoformat(request.end_datetime),
    )


def extract_hourly_weather(
    *,
    date_text: str,
    start_time_text: str,
    end_time_text: str,
    weather_data: WeatherDataBundle,
) -> list[WeatherHourData]:
    window = parse_time_window(
        date_text=date_text,
        start_time_text=start_time_text,
        end_time_text=end_time_text,
    )
    return extract_hourly_weather_by_window(weather_data=weather_data, window=window)


def extract_hourly_weather_from_request(
    request: CruiseEvaluateRequest,
    weather_data: WeatherDataBundle,
) -> list[WeatherHourData]:
    window = TimeWindow(
        start_datetime=datetime.fromisoformat(request.start_datetime),
        end_datetime=datetime.fromisoformat(request.end_datetime),
    )
    return extract_hourly_weather_by_window(weather_data=weather_data, window=window)


def extract_hourly_weather_by_window(
    *,
    weather_data: WeatherDataBundle,
    window: TimeWindow,
) -> list[WeatherHourData]:
    selected_hours: list[WeatherHourData] = []
    # Naive request times are local wall times at the requested location,
    # retaining the previous extractor's provider-offset behavior.
    zone = APP_TIMEZONE
    if weather_data.location.timezone:
        try:
            zone = ZoneInfo(weather_data.location.timezone)
        except ZoneInfoNotFoundError as exc:
            raise WeatherDataError("天气地点的时区数据异常，本次无法完成评估。", error_code="WEATHER_DATA_INVALID") from exc
    elif weather_data.hourly_weather:
        zone = forecast_datetime(weather_data.hourly_weather[0].fx_time).tzinfo or APP_TIMEZONE
    start = window.start_datetime
    end = window.end_datetime
    start = weather_datetime((start.replace(tzinfo=zone) if start.tzinfo is None else start).isoformat())
    end = weather_datetime((end.replace(tzinfo=zone) if end.tzinfo is None else end).isoformat())

    for hour in weather_data.hourly_weather:
        hour_start = weather_datetime(hour.fx_time)
        hour_end = hour_start + timedelta(hours=1)
        if _intersects(
            left_start=hour_start,
            left_end=hour_end,
            right_start=start,
            right_end=end,
        ):
            selected_hours.append(hour)

    if not selected_hours and weather_data.hourly_weather:
        raise WeatherDataError(
            "当前预报未覆盖所选时段，本次无法完成评估，请调整日期或时间。",
            error_code="WEATHER_FORECAST_OUT_OF_RANGE", retryable=False,
        )
    validate_window_coverage(selected_hours, start, end)
    return sorted(selected_hours, key=lambda hour: weather_datetime(hour.fx_time))


def _intersects(
    *,
    left_start: datetime,
    left_end: datetime,
    right_start: datetime,
    right_end: datetime,
) -> bool:
    return left_start < right_end and right_start < left_end
