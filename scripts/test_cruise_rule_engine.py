from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.rules import assess_cruise_window
from app.schemas.assessment import RiskDecision
from app.schemas.warning import WarningData, WarningDataBundle
from app.schemas.weather import LocationInfo, WeatherDataBundle, WeatherHourData


def build_weather_data() -> WeatherDataBundle:
    return WeatherDataBundle(
        location=LocationInfo(
            location_id="101280601",
            name="深圳",
            latitude="22.5431",
            longitude="114.0579",
        ),
        update_time="2026-07-05T05:00:00+08:00",
        hourly_weather=[
            WeatherHourData(
                fx_time="2026-07-05T06:00:00+08:00",
                temp="29",
                text="雷阵雨",
                wind_scale="1-3",
                wind_speed="7",
                humidity="82",
                precip="0.24",
                pop="70",
                pressure="998",
                cloud="92",
            ),
            WeatherHourData(
                fx_time="2026-07-05T07:00:00+08:00",
                temp="30",
                text="晴",
                wind_scale="1-2",
                wind_speed="4",
                humidity="60",
                precip="0",
                pop="10",
                pressure="1000",
                cloud="10",
            ),
            WeatherHourData(
                fx_time="2026-07-05T08:00:00+08:00",
                temp="31",
                text="多云",
                wind_scale="2",
                wind_speed="5",
                humidity="58",
                precip="0",
                pop="15",
                pressure="1001",
                cloud="35",
            ),
        ],
    )


def build_warning_bundle(level: str) -> WarningDataBundle:
    return WarningDataBundle(
        warnings=[
            WarningData(
                warning_id="w-1",
                event_type="雷电",
                warning_level=level,
                title="雷电预警",
                text="测试预警",
            )
        ],
        has_warning=True,
        warning_count=1,
    )


def main() -> None:
    weather_data = build_weather_data()

    base_result = assess_cruise_window(weather_data.hourly_weather)
    assert base_result.overall_decision == RiskDecision.PROHIBITED
    assert base_result.allow_cruise is False
    assert base_result.hourly_assessment[0].decision == RiskDecision.PROHIBITED
    assert "天气为雷阵雨" in base_result.hourly_assessment[0].risk_factors
    assert "降水概率高" in base_result.hourly_assessment[0].risk_factors

    yellow_result = assess_cruise_window(weather_data.hourly_weather, build_warning_bundle("yellow"))
    assert yellow_result.overall_decision == RiskDecision.PROHIBITED
    assert yellow_result.hourly_assessment[1].decision == RiskDecision.CAUTION
    assert "高风险预警：雷电yellow" in yellow_result.hourly_assessment[1].risk_factors

    orange_result = assess_cruise_window(weather_data.hourly_weather, build_warning_bundle("orange"))
    assert orange_result.overall_decision == RiskDecision.PROHIBITED
    assert orange_result.hourly_assessment[1].decision == RiskDecision.PROHIBITED
    assert "高风险预警：雷电orange" in orange_result.hourly_assessment[1].risk_factors

    print("base overall:", base_result.overall_decision)
    print("base first hour:", base_result.hourly_assessment[0].decision, base_result.hourly_assessment[0].risk_factors)
    print("yellow overall:", yellow_result.overall_decision)
    print("yellow second hour:", yellow_result.hourly_assessment[1].decision, yellow_result.hourly_assessment[1].risk_factors)
    print("orange overall:", orange_result.overall_decision)
    print("orange second hour:", orange_result.hourly_assessment[1].decision, orange_result.hourly_assessment[1].risk_factors)
    print("rule engine assertions passed")


if __name__ == "__main__":
    main()
