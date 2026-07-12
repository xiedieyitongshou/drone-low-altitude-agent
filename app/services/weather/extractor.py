from dataclasses import dataclass
from datetime import datetime, timedelta

from app.schemas.request import CruiseEvaluateRequest
from app.schemas.weather import WeatherDataBundle, WeatherHourData


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
    normalized_window = window

    for hour in weather_data.hourly_weather:
        hour_start = datetime.fromisoformat(hour.fx_time)
        hour_end = hour_start + timedelta(hours=1)
        normalized_window = _align_window_timezone(window=window, hour_start=hour_start)
        if _intersects(
            left_start=hour_start,
            left_end=hour_end,
            right_start=normalized_window.start_datetime,
            right_end=normalized_window.end_datetime,
        ):
            selected_hours.append(hour)

    return selected_hours


def _intersects(
    *,
    left_start: datetime,
    left_end: datetime,
    right_start: datetime,
    right_end: datetime,
) -> bool:
    return left_start < right_end and right_start < left_end


def _align_window_timezone(*, window: TimeWindow, hour_start: datetime) -> TimeWindow:
    if hour_start.tzinfo is None:
        return window
    if window.start_datetime.tzinfo is not None and window.end_datetime.tzinfo is not None:
        return window
    return TimeWindow(
        start_datetime=window.start_datetime.replace(tzinfo=hour_start.tzinfo),
        end_datetime=window.end_datetime.replace(tzinfo=hour_start.tzinfo),
    )
