from datetime import datetime

import pytest

from app.rules.cruise import assess_cruise_window, assess_hourly_weather, summarize_assessment
from app.schemas.weather import LocationInfo, WeatherDataBundle, WeatherHourData
from app.services.weather.exceptions import WeatherDataError
from app.services.weather.extractor import extract_hourly_weather
from app.services.weather.validation import validate_window_coverage


def hour(time="2026-11-23T14:00:00+08:00", **changes):
    values = dict(fx_time=time, text="晴", wind_speed="5", wind_scale="1-3", precip="0", pop="0", humidity="50")
    return WeatherHourData(**(values | changes))


def bundle(hours):
    return WeatherDataBundle(
        location=LocationInfo(location_id="fixture", name="深圳", latitude="22.5", longitude="114"),
        hourly_weather=hours,
    )


@pytest.mark.parametrize("field", ["text", "wind_speed", "wind_scale", "precip", "pop", "humidity"])
@pytest.mark.parametrize("value", [None, "", " "])
def test_missing_rule_metric_prevents_any_flight_decision(field, value):
    with pytest.raises(WeatherDataError) as caught:
        assess_hourly_weather(hour(**{field: value}))
    assert caught.value.error_code == "WEATHER_DATA_INCOMPLETE"
    assert caught.value.details[0]["field"] == field


@pytest.mark.parametrize("field,value", [
    ("wind_speed", "NaN"), ("wind_speed", "inf"), ("wind_speed", "-1"), ("precip", "bad"),
    ("precip", "-0.1"), ("humidity", "101"), ("pop", "-1"), ("pop", "101"),
    ("wind_scale", "3-1"), ("wind_scale", "18"), ("wind_scale", "bad"),
])
def test_invalid_rule_metric_is_not_silently_skipped(field, value):
    with pytest.raises(WeatherDataError) as caught:
        assess_cruise_window([hour(**{field: value})])
    assert caught.value.error_code == "WEATHER_DATA_INVALID"


def test_optional_metrics_and_zeroes_are_valid():
    result = assess_cruise_window([hour(wind_speed="0", wind_scale="0", humidity="0", temp=None, pressure=None, cloud=None)])
    assert result.allow_cruise is True


def test_empty_summary_cannot_bypass_data_validation():
    with pytest.raises(WeatherDataError):
        summarize_assessment([])


@pytest.mark.parametrize("times", [[14], [15, 16], [14, 16], [14, 15]])
def test_leading_internal_and_trailing_gaps_reject_the_whole_requested_window(times):
    with pytest.raises(WeatherDataError) as caught:
        extract_hourly_weather(
            date_text="2026-11-23", start_time_text="14:00", end_time_text="17:00",
            weather_data=bundle([hour(f"2026-11-23T{time}:00:00+08:00") for time in times]),
        )
    assert caught.value.details[0]["field"] == "hourly_weather"
    assert caught.value.error_code == "WEATHER_DATA_INCOMPLETE"


def test_only_requested_hours_require_complete_metrics_and_order_is_normalized():
    data = bundle([hour("2026-11-23T16:00:00+08:00"), hour(), hour("2026-11-23T15:00:00+08:00"),
                   WeatherHourData(fx_time="2026-11-23T20:00:00+08:00")])
    selected = extract_hourly_weather(date_text="2026-11-23", start_time_text="14:15", end_time_text="16:30", weather_data=data)
    result = assess_cruise_window(selected)
    assert len(result.hourly_assessment) == 3 and result.allow_cruise
    assert [x.fx_time[11:13] for x in selected] == ["14", "15", "16"]


def test_duplicate_hours_do_not_make_missing_hours_complete():
    with pytest.raises(WeatherDataError):
        assess_cruise_window([hour(), hour()])


def test_coverage_compares_instants_across_timezones():
    validate_window_coverage(
        [hour("2026-11-23T06:00:00+00:00")],
        datetime.fromisoformat("2026-11-23T14:15:00+08:00"),
        datetime.fromisoformat("2026-11-23T15:00:00+08:00"),
    )


def test_naive_request_keeps_the_locations_provider_timezone():
    selected = extract_hourly_weather(
        date_text="2026-11-23", start_time_text="14:00", end_time_text="15:00",
        weather_data=bundle([hour("2026-11-23T14:00:00-05:00")]),
    )
    assert len(selected) == 1 and selected[0].fx_time.endswith("-05:00")


def test_named_location_timezone_accepts_utc_forecast_timestamps():
    data = bundle([hour("2026-11-23T19:00:00+00:00")])
    data.location.timezone = "America/New_York"
    selected = extract_hourly_weather(
        date_text="2026-11-23", start_time_text="14:00", end_time_text="15:00", weather_data=data,
    )
    assert len(selected) == 1
