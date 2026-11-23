"""Validate only the weather hours used by the current business operation."""

import math
import re
from datetime import datetime, timedelta

from app.schemas.weather import WeatherHourData
from app.services.weather.exceptions import WeatherDataError
from app.utils.timezone import APP_TIMEZONE


# Every current mission profile evaluates these metrics. Display-only metrics
# (temperature, pressure and cloud) deliberately remain optional.
REQUIRED_WEATHER_FIELDS = ("text", "wind_speed", "wind_scale", "precip", "pop", "humidity")
FIELD_NAMES = {
    "text": "天气现象", "wind_speed": "风速", "wind_scale": "风力",
    "precip": "降水量", "pop": "降水概率", "humidity": "湿度",
}
HOUR = timedelta(hours=1)


def forecast_datetime(value: str) -> datetime:
    try:
        if len(value) <= 10:
            raise ValueError("forecast time must include a clock time")
        parsed = datetime.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise WeatherDataError(
            "天气时间格式异常，本次无法完成评估。", error_code="WEATHER_DATA_INVALID",
            details=[{"field": "fx_time", "message": "预报时间缺失或无法解析"}],
        ) from exc
    return parsed


def weather_datetime(value: str) -> datetime:
    parsed = forecast_datetime(value)
    return parsed.replace(tzinfo=APP_TIMEZONE) if parsed.tzinfo is None else parsed.astimezone(APP_TIMEZONE)


def validate_weather_hour(hour: WeatherHourData) -> None:
    weather_datetime(hour.fx_time)
    issues = []
    has_invalid_number = False
    for field in REQUIRED_WEATHER_FIELDS:
        value = getattr(hour, field)
        if value is None or not value.strip():
            issues.append({"field": field, "message": f"{hour.fx_time} 缺少{FIELD_NAMES[field]}"})
            continue
        if field == "text":
            continue
        if field == "wind_scale":
            match = re.fullmatch(r"(\d{1,2})(?:-(\d{1,2}))?", value.strip())
            valid = bool(match) and 0 <= int(match[1]) <= int(match[2] or match[1]) <= 17
        else:
            try:
                number = float(value)
                valid = math.isfinite(number) and number >= 0
                if field in {"pop", "humidity"}:
                    valid = valid and number <= 100
            except ValueError:
                valid = False
        if not valid:
            has_invalid_number = True
            issues.append({"field": field, "message": f"{hour.fx_time} 的{FIELD_NAMES[field]}数值异常"})
    if issues:
        raise WeatherDataError(
            f"天气数据缺失或异常，本次无法完成评估：{issues[0]['message']}。",
            error_code="WEATHER_DATA_INVALID" if has_invalid_number else "WEATHER_DATA_INCOMPLETE",
            details=issues,
        )


def validate_weather_sequence(hours: list[WeatherHourData]) -> None:
    if not hours:
        raise WeatherDataError("没有可用的逐小时天气数据，本次无法完成评估。")
    times = []
    for hour in hours:
        validate_weather_hour(hour)
        times.append(weather_datetime(hour.fx_time))
    if len(times) != len(set(times)):
        raise WeatherDataError("逐小时天气时间重复，本次无法完成评估。", error_code="WEATHER_DATA_INVALID")
    ordered = sorted(times)
    validate_window_coverage(hours, ordered[0], ordered[-1] + HOUR)


def validate_window_coverage(hours: list[WeatherHourData], start: datetime, end: datetime) -> None:
    start = weather_datetime(start.isoformat())
    end = weather_datetime(end.isoformat())
    cursor = start
    gaps = []
    for hour in sorted(hours, key=lambda item: weather_datetime(item.fx_time)):
        hour_start = weather_datetime(hour.fx_time)
        hour_end = hour_start + HOUR
        if hour_end <= start or hour_start >= end:
            continue
        if hour_start > cursor:
            gaps.append((cursor, min(hour_start, end)))
        cursor = max(cursor, min(hour_end, end))
    if cursor < end:
        gaps.append((cursor, end))
    if gaps:
        details = [{"field": "hourly_weather", "message": f"缺少 {left.isoformat()} 至 {right.isoformat()} 的天气数据"}
                   for left, right in gaps[:20]]
        raise WeatherDataError(
            f"所选时段天气数据不完整，本次无法完成评估：{details[0]['message']}。", details=details,
        )
