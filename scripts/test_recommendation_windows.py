from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.schemas.assessment import HourlyAssessment, RiskDecision
from app.services.recommendation import build_recommendation_result


def main() -> None:
    hourly_assessment = [
        HourlyAssessment(fx_time="2026-07-14T06:00:00+08:00", decision=RiskDecision.SUITABLE),
        HourlyAssessment(fx_time="2026-07-14T07:00:00+08:00", decision=RiskDecision.SUITABLE),
        HourlyAssessment(
            fx_time="2026-07-14T08:00:00+08:00",
            decision=RiskDecision.CAUTION,
            risk_factors=["风速中等偏高"],
        ),
        HourlyAssessment(fx_time="2026-07-14T09:00:00+08:00", decision=RiskDecision.SUITABLE),
        HourlyAssessment(fx_time="2026-07-14T10:00:00+08:00", decision=RiskDecision.SUITABLE),
        HourlyAssessment(
            fx_time="2026-07-14T11:00:00+08:00",
            decision=RiskDecision.PROHIBITED,
            risk_factors=["高风险预警：雷电orange"],
        ),
        HourlyAssessment(fx_time="2026-07-14T12:00:00+08:00", decision=RiskDecision.SUITABLE),
        HourlyAssessment(fx_time="2026-07-14T13:00:00+08:00", decision=RiskDecision.SUITABLE),
    ]

    result = build_recommendation_result(hourly_assessment)
    print("strategy:", result.strategy.model_dump())
    print("total_candidates:", result.total_candidates)
    for window in result.recommended_windows:
        print(window.rank, window.start_time, window.end_time, window.overall_decision, window.risk_score)


if __name__ == "__main__":
    main()
