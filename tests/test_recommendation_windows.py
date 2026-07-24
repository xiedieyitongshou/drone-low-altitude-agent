from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.schemas.assessment import HourlyAssessment, RiskDecision
from app.services.recommendation.window_recommender import (
    RecommendationConfig,
    build_recommendation_result,
)


class RecommendationWindowTestCase(unittest.TestCase):
    def test_continuous_executable_segment_generates_one_window(self) -> None:
        hourly_assessment = [
            HourlyAssessment(fx_time=f"2026-07-14T{hour:02d}:00:00+08:00", decision=RiskDecision.SUITABLE)
            for hour in range(6, 14)
        ]

        result = build_recommendation_result(
            hourly_assessment,
            RecommendationConfig(min_window_hours=2, max_recommendations=5),
        )

        self.assertEqual(result.total_candidates, 1)
        self.assertEqual(len(result.recommended_windows), 1)
        self.assertEqual(result.recommended_windows[0].start_time, "2026-07-14T06:00:00+08:00")
        self.assertEqual(result.recommended_windows[0].end_time, "2026-07-14T14:00:00+08:00")

        occupied_hours: set[str] = set()
        for window in result.recommended_windows:
            window_hours = {item.fx_time for item in window.hourly_assessment}
            self.assertTrue(window_hours.isdisjoint(occupied_hours))
            occupied_hours.update(window_hours)

    def test_prohibited_hours_split_executable_segments(self) -> None:
        hourly_assessment = [
            HourlyAssessment(fx_time="2026-07-14T06:00:00+08:00", decision=RiskDecision.SUITABLE),
            HourlyAssessment(fx_time="2026-07-14T07:00:00+08:00", decision=RiskDecision.SUITABLE),
            HourlyAssessment(fx_time="2026-07-14T08:00:00+08:00", decision=RiskDecision.SUITABLE),
            HourlyAssessment(fx_time="2026-07-14T09:00:00+08:00", decision=RiskDecision.PROHIBITED),
            HourlyAssessment(fx_time="2026-07-14T10:00:00+08:00", decision=RiskDecision.SUITABLE),
            HourlyAssessment(fx_time="2026-07-14T11:00:00+08:00", decision=RiskDecision.SUITABLE),
        ]

        result = build_recommendation_result(
            hourly_assessment,
            RecommendationConfig(min_window_hours=2, max_recommendations=5),
        )

        self.assertEqual(result.total_candidates, 2)
        self.assertEqual(len(result.recommended_windows), 2)
        self.assertEqual(result.recommended_windows[0].start_time, "2026-07-14T06:00:00+08:00")
        self.assertEqual(result.recommended_windows[0].end_time, "2026-07-14T09:00:00+08:00")
        self.assertEqual(result.recommended_windows[1].start_time, "2026-07-14T10:00:00+08:00")
        self.assertEqual(result.recommended_windows[1].end_time, "2026-07-14T12:00:00+08:00")

    def test_discontinuous_hours_split_executable_segments(self) -> None:
        hourly_assessment = [
            HourlyAssessment(fx_time="2026-07-14T06:00:00+08:00", decision=RiskDecision.SUITABLE),
            HourlyAssessment(fx_time="2026-07-14T07:00:00+08:00", decision=RiskDecision.SUITABLE),
            HourlyAssessment(fx_time="2026-07-14T10:00:00+08:00", decision=RiskDecision.SUITABLE),
            HourlyAssessment(fx_time="2026-07-14T11:00:00+08:00", decision=RiskDecision.SUITABLE),
        ]

        result = build_recommendation_result(
            hourly_assessment,
            RecommendationConfig(min_window_hours=2, max_recommendations=5),
        )

        self.assertEqual(result.total_candidates, 2)
        self.assertEqual(result.recommended_windows[0].start_time, "2026-07-14T06:00:00+08:00")
        self.assertEqual(result.recommended_windows[0].end_time, "2026-07-14T08:00:00+08:00")
        self.assertEqual(result.recommended_windows[1].start_time, "2026-07-14T10:00:00+08:00")
        self.assertEqual(result.recommended_windows[1].end_time, "2026-07-14T12:00:00+08:00")


if __name__ == "__main__":
    unittest.main()
