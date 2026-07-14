from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from app.schemas import ComparedLocationResult, HourlyAssessment, MultiLocationComparisonRequest, MultiLocationComparisonResponse, RecommendationWindow, RiskDecision
from app.services.comparison.comparison_profiles import ComparisonWeightProfile, get_comparison_weight_profile
from app.services.cruise_evaluator import build_cruise_request, evaluate_cruise_request


def compare_locations(payload: MultiLocationComparisonRequest) -> MultiLocationComparisonResponse:
    comparisons: list[ComparedLocationResult] = []
    max_workers = min(4, len(payload.locations))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_location = {
            executor.submit(
                _evaluate_single_location,
                location,
                payload.date,
                payload.start_time,
                payload.end_time,
                payload.task_type,
                payload.purpose,
            ): location
            for location in payload.locations
        }

        for future in as_completed(future_to_location):
            location = future_to_location[future]
            try:
                comparisons.append(future.result())
            except Exception as exc:
                comparisons.append(
                    ComparedLocationResult(
                        rank=0,
                        location=location,
                        available=False,
                        error_message=str(exc),
                    )
                )

    weight_profile = get_comparison_weight_profile(payload.comparison_mode)
    _apply_comparison_scores(comparisons, weight_profile)

    ranked = sorted(
        comparisons,
        key=lambda item: (
            1 if not item.available else 0,
            _decision_priority(item.overall_decision),
            -(item.score if item.score is not None else -1),
            item.location,
        ),
    )

    for index, item in enumerate(ranked, start=1):
        item.rank = index

    top_k_locations = ranked[: payload.top_k]
    return MultiLocationComparisonResponse(
        request={
            "locations": payload.locations,
            "date": payload.date,
            "start_time": payload.start_time,
            "end_time": payload.end_time,
            "task_type": payload.task_type,
            "purpose": payload.purpose,
            "top_k": payload.top_k,
            "comparison_mode": payload.comparison_mode,
        },
        comparisons=ranked,
        top_k_locations=top_k_locations,
        recommended_location=ranked[0] if ranked else None,
    )


def _evaluate_single_location(
    location: str,
    date_text: str,
    start_time: str,
    end_time: str,
    task_type: str,
    purpose: str | None,
) -> ComparedLocationResult:
    request = build_cruise_request(
        location=location,
        date=date_text,
        start_time=start_time,
        end_time=end_time,
        task_type=task_type,
        purpose=purpose,
    )
    result = evaluate_cruise_request(request)
    risk_score = _calculate_risk_score(result.advice)
    location_id = result.weather.location.location_id if result.weather else None
    flyable_hour_count = _calculate_flyable_hour_count(result.advice.hourly_assessment)
    max_continuous_flyable_hours = _calculate_max_continuous_flyable_hours(result.advice.hourly_assessment)
    earliest_flyable_time = _find_earliest_flyable_time(result.advice.hourly_assessment)
    best_window = _build_best_window(result.advice.hourly_assessment)
    window_quality_score = _calculate_window_quality_score(best_window)

    return ComparedLocationResult(
        rank=0,
        location=location,
        available=True,
        location_id=location_id,
        overall_decision=result.advice.overall_decision,
        allow_cruise=result.advice.allow_cruise,
        risk_score=risk_score,
        flyable_hour_count=flyable_hour_count,
        max_continuous_flyable_hours=max_continuous_flyable_hours,
        earliest_flyable_time=earliest_flyable_time,
        window_quality_score=window_quality_score,
        best_window=best_window,
        summary_risk_factors=result.advice.summary_risk_factors,
        advice=result.advice,
    )


def _calculate_risk_score(advice) -> int:
    base_score = 0
    if advice.overall_decision == RiskDecision.CAUTION:
        base_score = 100
    elif advice.overall_decision == RiskDecision.PROHIBITED:
        base_score = 200
    return base_score + sum(len(item.risk_factors) for item in advice.hourly_assessment)


def _decision_priority(decision: RiskDecision | None) -> int:
    if decision == RiskDecision.SUITABLE:
        return 0
    if decision == RiskDecision.CAUTION:
        return 1
    if decision == RiskDecision.PROHIBITED:
        return 2
    return 3


def _apply_comparison_scores(
    comparisons: list[ComparedLocationResult],
    weight_profile: ComparisonWeightProfile,
) -> None:
    available_results = [item for item in comparisons if item.available]
    if not available_results:
        return

    max_flyable_hours = max(item.flyable_hour_count for item in available_results) or 1
    max_continuous_hours = max(item.max_continuous_flyable_hours for item in available_results) or 1
    max_window_quality = max((item.window_quality_score or 0) for item in available_results) or 1
    earliest_values = [
        _earliest_minutes(item.earliest_flyable_time)
        for item in available_results
        if item.earliest_flyable_time is not None
    ]
    min_earliest = min(earliest_values) if earliest_values else None
    max_earliest = max(earliest_values) if earliest_values else None

    for item in available_results:
        flyable_component = _normalize_positive(item.flyable_hour_count, max_flyable_hours)
        continuous_component = _normalize_positive(item.max_continuous_flyable_hours, max_continuous_hours)
        earliest_component = _normalize_earliest(item.earliest_flyable_time, min_earliest, max_earliest)
        window_quality_component = _normalize_positive(item.window_quality_score or 0, max_window_quality)

        score = (
            flyable_component * weight_profile.flyable_hour_count_weight
            + continuous_component * weight_profile.max_continuous_flyable_hours_weight
            + earliest_component * weight_profile.earliest_flyable_time_weight
            + window_quality_component * weight_profile.window_quality_weight
        )

        item.score = round(score * 100, 2)
        item.score_breakdown = {
            "flyable_hour_count": round(flyable_component * 100, 2),
            "max_continuous_flyable_hours": round(continuous_component * 100, 2),
            "earliest_flyable_time": round(earliest_component * 100, 2),
            "window_quality": round(window_quality_component * 100, 2),
        }


def _calculate_flyable_hour_count(hourly_assessment: list[HourlyAssessment]) -> int:
    return sum(1 for item in hourly_assessment if item.decision == RiskDecision.SUITABLE)


def _calculate_max_continuous_flyable_hours(hourly_assessment: list[HourlyAssessment]) -> int:
    longest = 0
    current = 0
    previous_time: datetime | None = None

    for item in sorted(hourly_assessment, key=lambda hour: hour.fx_time):
        item_time = datetime.fromisoformat(item.fx_time)
        if item.decision == RiskDecision.SUITABLE:
            if previous_time is not None and item_time - previous_time == timedelta(hours=1):
                current += 1
            else:
                current = 1
        else:
            current = 0
        previous_time = item_time
        if current > longest:
            longest = current
    return longest


def _find_earliest_flyable_time(hourly_assessment: list[HourlyAssessment]) -> str | None:
    suitable_items = [item.fx_time for item in hourly_assessment if item.decision == RiskDecision.SUITABLE]
    return min(suitable_items) if suitable_items else None


def _build_best_window(hourly_assessment: list[HourlyAssessment]) -> RecommendationWindow | None:
    sequences: list[list[HourlyAssessment]] = []
    current: list[HourlyAssessment] = []
    previous_time: datetime | None = None

    for item in sorted(hourly_assessment, key=lambda hour: hour.fx_time):
        item_time = datetime.fromisoformat(item.fx_time)
        if item.decision == RiskDecision.SUITABLE:
            if current and previous_time and item_time - previous_time != timedelta(hours=1):
                sequences.append(current)
                current = [item]
            else:
                current.append(item)
        else:
            if current:
                sequences.append(current)
                current = []
        previous_time = item_time

    if current:
        sequences.append(current)

    if not sequences:
        return None

    sequences.sort(key=lambda seq: (-len(seq), seq[0].fx_time))
    best_sequence = sequences[0]
    return RecommendationWindow(
        rank=1,
        start_time=best_sequence[0].fx_time,
        end_time=(datetime.fromisoformat(best_sequence[-1].fx_time) + timedelta(hours=1)).isoformat(),
        duration_hours=len(best_sequence),
        overall_decision=RiskDecision.SUITABLE,
        risk_score=0,
        reasons=["窗口内小时结果均为适飞"],
        hourly_assessment=best_sequence,
    )


def _calculate_window_quality_score(best_window: RecommendationWindow | None) -> float:
    if best_window is None:
        return 0.0
    return float(best_window.duration_hours * 100 - best_window.risk_score)


def _normalize_positive(value: float, max_value: float) -> float:
    if max_value <= 0:
        return 0.0
    return value / max_value


def _normalize_earliest(value: str | None, minimum: int | None, maximum: int | None) -> float:
    if value is None or minimum is None or maximum is None:
        return 0.0
    current = _earliest_minutes(value)
    if maximum == minimum:
        return 1.0
    return (maximum - current) / (maximum - minimum)


def _earliest_minutes(value: str) -> int:
    item_time = datetime.fromisoformat(value)
    return item_time.hour * 60 + item_time.minute
