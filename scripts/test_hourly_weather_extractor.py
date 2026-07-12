from pathlib import Path
import sys

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


def main() -> None:
    sample_weather = build_sample_weather()

    direct_result = extract_hourly_weather(
        date_text="2026-07-09",
        start_time_text="23:00",
        end_time_text="01:00",
        weather_data=sample_weather,
    )
    print("direct_result:", [item.fx_time for item in direct_result])

    request = CruiseEvaluateRequest(
        location="深圳湾",
        date="2026-07-09",
        start_time="23:00",
        end_time="01:00",
        task_type="cruise",
    )
    request_result = extract_hourly_weather_from_request(request, sample_weather)
    print("request_result:", [item.fx_time for item in request_result])


if __name__ == "__main__":
    main()
