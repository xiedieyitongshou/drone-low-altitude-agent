from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.rules import assess_cruise_window
from app.schemas.assessment import RiskDecision
from app.schemas.warning import WarningData, WarningDataBundle
from app.schemas.weather import WeatherHourData


def build_warning_bundle(level: str, event_type: str = "雷电") -> WarningDataBundle:
    return WarningDataBundle(
        warnings=[
            WarningData(
                warning_id="warning-1",
                event_type=event_type,
                warning_level=level,
                title="测试预警",
                text="测试说明",
            )
        ],
        has_warning=True,
        warning_count=1,
    )


class RuleEngineTestCase(unittest.TestCase):
    def test_weather_rule_marks_prohibited(self) -> None:
        result = assess_cruise_window(
            [
                WeatherHourData(
                    fx_time="2026-07-05T06:00:00+08:00",
                    text="雷阵雨",
                    precip="0.24",
                    pop="70",
                    wind_speed="7",
                    wind_scale="1-3",
                    humidity="82",
                )
            ]
        )

        self.assertEqual(result.overall_decision, RiskDecision.PROHIBITED)
        self.assertFalse(result.allow_cruise)
        self.assertIn("天气为雷阵雨", result.hourly_assessment[0].risk_factors)
        self.assertIn("降水概率高", result.hourly_assessment[0].risk_factors)

    def test_weather_rule_marks_caution(self) -> None:
        result = assess_cruise_window(
            [
                WeatherHourData(
                    fx_time="2026-07-05T07:00:00+08:00",
                    text="阴",
                    precip="0.10",
                    pop="50",
                    wind_speed="8",
                    wind_scale="1-3",
                    humidity="86",
                )
            ]
        )

        self.assertEqual(result.overall_decision, RiskDecision.CAUTION)
        self.assertFalse(result.allow_cruise)
        self.assertIn("天气为阴", result.hourly_assessment[0].risk_factors)
        self.assertIn("存在轻中度降水", result.hourly_assessment[0].risk_factors)
        self.assertIn("降水概率中等", result.hourly_assessment[0].risk_factors)

    def test_warning_adjustment_yellow_upgrades_suitable_to_caution(self) -> None:
        result = assess_cruise_window(
            [
                WeatherHourData(
                    fx_time="2026-07-05T08:00:00+08:00",
                    text="晴",
                    precip="0",
                    pop="10",
                    wind_speed="4",
                    wind_scale="1-2",
                    humidity="60",
                )
            ],
            build_warning_bundle("yellow"),
        )

        self.assertEqual(result.overall_decision, RiskDecision.CAUTION)
        self.assertEqual(result.hourly_assessment[0].decision, RiskDecision.CAUTION)
        self.assertIn("高风险预警：雷电yellow", result.hourly_assessment[0].risk_factors)

    def test_warning_adjustment_orange_forces_prohibited(self) -> None:
        result = assess_cruise_window(
            [
                WeatherHourData(
                    fx_time="2026-07-05T08:00:00+08:00",
                    text="晴",
                    precip="0",
                    pop="10",
                    wind_speed="4",
                    wind_scale="1-2",
                    humidity="60",
                )
            ],
            build_warning_bundle("orange"),
        )

        self.assertEqual(result.overall_decision, RiskDecision.PROHIBITED)
        self.assertEqual(result.hourly_assessment[0].decision, RiskDecision.PROHIBITED)
        self.assertIn("高风险预警：雷电orange", result.hourly_assessment[0].risk_factors)

    def test_non_high_risk_warning_does_not_change_result(self) -> None:
        result = assess_cruise_window(
            [
                WeatherHourData(
                    fx_time="2026-07-05T08:00:00+08:00",
                    text="晴",
                    precip="0",
                    pop="10",
                    wind_speed="4",
                    wind_scale="1-2",
                    humidity="60",
                )
            ],
            build_warning_bundle("orange", event_type="高温"),
        )

        self.assertEqual(result.overall_decision, RiskDecision.SUITABLE)
        self.assertEqual(result.hourly_assessment[0].risk_factors, [])

    def test_wind_scale_range_one_to_three_is_treated_as_level_two(self) -> None:
        result = assess_cruise_window(
            [
                WeatherHourData(
                    fx_time="2026-07-05T08:00:00+08:00",
                    text="晴",
                    precip="0",
                    pop="10",
                    wind_speed="4",
                    wind_scale="1-3",
                    humidity="60",
                )
            ]
        )

        self.assertEqual(result.overall_decision, RiskDecision.SUITABLE)
        self.assertNotIn("风力等级中等", result.hourly_assessment[0].risk_factors)

    def test_single_wind_scale_three_keeps_original_level(self) -> None:
        result = assess_cruise_window(
            [
                WeatherHourData(
                    fx_time="2026-07-05T08:00:00+08:00",
                    text="晴",
                    precip="0",
                    pop="10",
                    wind_speed="4",
                    wind_scale="3",
                    humidity="60",
                )
            ]
        )

        self.assertEqual(result.overall_decision, RiskDecision.CAUTION)
        self.assertIn("风力等级中等", result.hourly_assessment[0].risk_factors)

    def test_wind_speed_under_fifteen_kmh_is_suitable(self) -> None:
        result = assess_cruise_window(
            [
                WeatherHourData(
                    fx_time="2026-07-05T08:00:00+08:00",
                    text="晴",
                    precip="0",
                    pop="10",
                    wind_speed="14",
                    wind_scale="1-2",
                    humidity="60",
                )
            ]
        )

        self.assertEqual(result.overall_decision, RiskDecision.SUITABLE)
        self.assertNotIn("风速中等偏高", result.hourly_assessment[0].risk_factors)

    def test_wind_speed_between_fifteen_and_twenty_five_kmh_is_caution(self) -> None:
        result = assess_cruise_window(
            [
                WeatherHourData(
                    fx_time="2026-07-05T08:00:00+08:00",
                    text="晴",
                    precip="0",
                    pop="10",
                    wind_speed="16",
                    wind_scale="1-2",
                    humidity="60",
                )
            ]
        )

        self.assertEqual(result.overall_decision, RiskDecision.CAUTION)
        self.assertIn("风速中等偏高", result.hourly_assessment[0].risk_factors)

    def test_wind_speed_at_twenty_five_kmh_is_prohibited(self) -> None:
        result = assess_cruise_window(
            [
                WeatherHourData(
                    fx_time="2026-07-05T08:00:00+08:00",
                    text="晴",
                    precip="0",
                    pop="10",
                    wind_speed="25",
                    wind_scale="1-2",
                    humidity="60",
                )
            ]
        )

        self.assertEqual(result.overall_decision, RiskDecision.PROHIBITED)
        self.assertIn("风速偏高", result.hourly_assessment[0].risk_factors)

    def test_empty_hourly_weather_returns_empty_assessment(self) -> None:
        result = assess_cruise_window([])

        self.assertEqual(result.overall_decision, RiskDecision.SUITABLE)
        self.assertTrue(result.allow_cruise)
        self.assertEqual(result.hourly_assessment, [])
        self.assertEqual(result.summary_risk_factors, [])


if __name__ == "__main__":
    unittest.main()
