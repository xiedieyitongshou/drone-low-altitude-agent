from dataclasses import dataclass
from datetime import datetime, timedelta

from app.schemas.assessment import HourlyAssessment, RiskDecision
from app.schemas.recommendation import RecommendationResult, RecommendationStrategy, RecommendationWindow


@dataclass(frozen=True)
class RecommendationConfig:
    min_window_hours: int = 2
    max_recommendations: int = 5


def recommend_execution_windows(
    hourly_assessment: list[HourlyAssessment],
    config: RecommendationConfig | None = None,
) -> list[RecommendationWindow]:
    active_config = config or RecommendationConfig()
    candidates = _generate_candidate_windows(hourly_assessment, active_config)
    top_windows = candidates[: active_config.max_recommendations]
    for index, window in enumerate(top_windows, start=1):
        window.rank = index
    return top_windows


def build_recommendation_result(
    hourly_assessment: list[HourlyAssessment],
    config: RecommendationConfig | None = None,
) -> RecommendationResult:
    active_config = config or RecommendationConfig()
    all_candidates = _generate_candidate_windows(hourly_assessment, active_config)
    windows = all_candidates[: active_config.max_recommendations]
    for index, window in enumerate(windows, start=1):
        window.rank = index
    return RecommendationResult(
        strategy=RecommendationStrategy(
            min_window_hours=active_config.min_window_hours,
            sort_rules=["适飞优先", "风险低优先", "连续性优先"],
        ),
        recommended_windows=windows,
        total_candidates=len(all_candidates),
    )


def _generate_candidate_windows(
    hourly_assessment: list[HourlyAssessment],
    config: RecommendationConfig,
) -> list[RecommendationWindow]:
    if config.min_window_hours <= 0:
        raise ValueError("min_window_hours must be greater than 0")
    if not hourly_assessment:
        return []

    candidates: list[RecommendationWindow] = []
    sorted_hours = sorted(hourly_assessment, key=lambda item: item.fx_time)
    current_segment: list[HourlyAssessment] = []

    for hour in sorted_hours:
        if hour.decision == RiskDecision.PROHIBITED:
            _append_segment_candidate(candidates, current_segment, config)
            current_segment = []
            continue

        if current_segment and not _is_next_hour(current_segment[-1], hour):
            _append_segment_candidate(candidates, current_segment, config)
            current_segment = []

        current_segment.append(hour)

    _append_segment_candidate(candidates, current_segment, config)

    ranked = sorted(
        candidates,
        key=lambda item: (
            _decision_priority(item.overall_decision),
            item.risk_score,
            -item.duration_hours,
            item.start_time,
        ),
    )
    return ranked


def _append_segment_candidate(
    candidates: list[RecommendationWindow],
    segment_hours: list[HourlyAssessment],
    config: RecommendationConfig,
) -> None:
    duration_hours = len(segment_hours)
    if duration_hours < config.min_window_hours:
        return

    overall_decision = _summarize_window_decision(segment_hours)
    risk_score = _calculate_risk_score(segment_hours, overall_decision)
    reasons = _build_window_reasons(segment_hours, overall_decision)
    candidates.append(
        RecommendationWindow(
            rank=0,
            start_time=segment_hours[0].fx_time,
            end_time=_shift_one_hour(segment_hours[-1].fx_time),
            duration_hours=duration_hours,
            overall_decision=overall_decision,
            risk_score=risk_score,
            reasons=reasons,
            hourly_assessment=segment_hours,
        )
    )


def _is_next_hour(current: HourlyAssessment, following: HourlyAssessment) -> bool:
    current_time = datetime.fromisoformat(current.fx_time)
    next_time = datetime.fromisoformat(following.fx_time)
    return next_time - current_time == timedelta(hours=1)


def _summarize_window_decision(window_hours: list[HourlyAssessment]) -> RiskDecision:
    if any(item.decision == RiskDecision.PROHIBITED for item in window_hours):
        return RiskDecision.PROHIBITED
    if any(item.decision == RiskDecision.CAUTION for item in window_hours):
        return RiskDecision.CAUTION
    return RiskDecision.SUITABLE


def _calculate_risk_score(window_hours: list[HourlyAssessment], overall_decision: RiskDecision) -> int:
    base_score = 0 if overall_decision == RiskDecision.SUITABLE else 100
    return base_score + sum(len(item.risk_factors) for item in window_hours)


def _build_window_reasons(window_hours: list[HourlyAssessment], overall_decision: RiskDecision) -> list[str]:
    reason_set: list[str] = []
    if overall_decision == RiskDecision.SUITABLE:
        reason_set.append("窗口内小时结果均为适飞")
    else:
        reason_set.append("窗口内存在慎飞小时")

    for item in window_hours:
        for risk_factor in item.risk_factors:
            if risk_factor not in reason_set:
                reason_set.append(risk_factor)
    return reason_set


def _decision_priority(decision: RiskDecision) -> int:
    if decision == RiskDecision.SUITABLE:
        return 0
    if decision == RiskDecision.CAUTION:
        return 1
    return 2


def _shift_one_hour(fx_time: str) -> str:
    return (datetime.fromisoformat(fx_time) + timedelta(hours=1)).isoformat()
