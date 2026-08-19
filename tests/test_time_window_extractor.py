from pathlib import Path
import sys
import unittest

from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.schemas.request import CruiseEvaluateRequest
from app.schemas.weather import LocationInfo, WeatherDataBundle, WeatherHourData
from app.services.weather import extract_hourly_weather, extract_hourly_weather_from_request


def build_sample_weather() -> WeatherDataBundle:
    return WeatherDataBundle(
        location=LocationInfo(
            location_id="101280601",
            name="深圳",
            latitude="22.54700",
            longitude="114.08595",
        ),
        hourly_weather=[
            WeatherHourData(fx_time="2026-07-09T22:00:00+08:00", text="晴"),
            WeatherHourData(fx_time="2026-07-09T23:00:00+08:00", text="晴"),
            WeatherHourData(fx_time="2026-07-10T00:00:00+08:00", text="晴"),
            WeatherHourData(fx_time="2026-07-10T01:00:00+08:00", text="晴"),
            WeatherHourData(fx_time="2026-07-10T02:00:00+08:00", text="晴"),
        ],
    )


class TimeWindowExtractorTestCase(unittest.TestCase):
    def test_cross_day_time_range_extracts_expected_hours(self) -> None:
        result = extract_hourly_weather(
            date_text="2026-07-09",
            start_time_text="23:00",
            end_time_text="01:00",
            weather_data=build_sample_weather(),
        )

        self.assertEqual(
            [item.fx_time for item in result],
            ["2026-07-09T23:00:00+08:00", "2026-07-10T00:00:00+08:00"],
        )

    def test_2400_end_time_extracts_until_midnight(self) -> None:
        result = extract_hourly_weather(
            date_text="2026-07-09",
            start_time_text="23:00",
            end_time_text="24:00",
            weather_data=build_sample_weather(),
        )

        self.assertEqual([item.fx_time for item in result], ["2026-07-09T23:00:00+08:00"])

    def test_request_model_marks_cross_day(self) -> None:
        request = CruiseEvaluateRequest(
            location="深圳湾",
            date="2026-07-09",
            start_time="23:00",
            end_time="01:00",
            task_type="cruise",
        )

        result = extract_hourly_weather_from_request(request, build_sample_weather())

        self.assertTrue(request.spans_next_day)
        self.assertEqual(request.start_datetime, "2026-07-09T23:00:00")
        self.assertEqual(request.end_datetime, "2026-07-10T01:00:00")
        self.assertEqual(len(result), 2)

    def test_invalid_start_time_2400_raises_validation_error(self) -> None:
        with self.assertRaises(ValidationError):
            CruiseEvaluateRequest(
                location="深圳湾",
                date="2026-07-09",
                start_time="24:00",
                end_time="01:00",
                task_type="cruise",
            )

    def test_no_matching_hours_returns_empty_list(self) -> None:
        result = extract_hourly_weather(
            date_text="2026-07-11",
            start_time_text="10:00",
            end_time_text="11:00",
            weather_data=build_sample_weather(),
        )

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
