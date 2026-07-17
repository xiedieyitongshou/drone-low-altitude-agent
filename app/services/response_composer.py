from app.schemas import (
    CruiseAssessmentResponse,
    CruiseHistoryResponse,
    MultiLocationComparisonResponse,
    RecommendationResponse,
)
from app.schemas.composed_response import (
    ComposedHistorySummary,
    ComposedLocationRanking,
    ComposedRecommendationWindow,
    UnifiedBusinessResponse,
)


def compose_evaluation_response(response: CruiseAssessmentResponse) -> UnifiedBusinessResponse:
    """Compose a stable evaluate-scene response for frontend and later LLM use."""

    request = response.request
    summary = (
        f"{request.get('location')} {request.get('date')} "
        f"{request.get('start_time')}-{request.get('end_time')} "
        f"任务结论为 {response.advice.overall_decision}。"
    )
    return UnifiedBusinessResponse(
        scene="evaluate",
        summary=summary,
        overall_decision=response.advice.overall_decision,
        allow_execute=response.advice.allow_cruise,
        risk_reasons=response.advice.summary_risk_factors,
        details={
            "request": response.request,
            "warning_count": response.warnings.warning_count if response.warnings else 0,
            "hour_count": len(response.advice.hourly_assessment),
        },
    )


def compose_recommendation_response(response: RecommendationResponse) -> UnifiedBusinessResponse:
    """Compose a stable recommend-scene response."""

    windows = [
        ComposedRecommendationWindow(
            rank=item.rank,
            start_time=item.start_time,
            end_time=item.end_time,
            duration_hours=item.duration_hours,
            overall_decision=item.overall_decision,
            risk_score=item.risk_score,
            reasons=item.reasons,
        )
        for item in response.recommendation.recommended_windows
    ]
    if windows:
        top = windows[0]
        summary = (
            f"{response.request.get('location')} 当前推荐窗口为 {top.start_time} 到 {top.end_time}，"
            f"结论为 {top.overall_decision}。"
        )
        overall_decision = top.overall_decision
        risk_reasons = top.reasons
    else:
        summary = f"{response.request.get('location')} 当前未发现满足条件的推荐窗口。"
        overall_decision = None
        risk_reasons = []

    return UnifiedBusinessResponse(
        scene="recommend",
        summary=summary,
        overall_decision=overall_decision,
        allow_execute=bool(windows),
        risk_reasons=risk_reasons,
        recommended_windows=windows,
        details={
            "request": response.request,
            "total_candidates": response.recommendation.total_candidates,
            "warning_count": response.warnings.warning_count if response.warnings else 0,
        },
    )


def compose_comparison_response(response: MultiLocationComparisonResponse) -> UnifiedBusinessResponse:
    """Compose a stable compare-scene response."""

    rankings = [
        ComposedLocationRanking(
            rank=item.rank,
            location=item.location,
            overall_decision=item.overall_decision,
            score=item.score,
            flyable_hour_count=item.flyable_hour_count,
            max_continuous_flyable_hours=item.max_continuous_flyable_hours,
            earliest_flyable_time=item.earliest_flyable_time,
            summary_reason=_build_location_reason(item),
        )
        for item in response.top_k_locations
    ]
    recommended = response.recommended_location
    summary = f"当前推荐优先地点为 {recommended.location}。" if recommended else "当前没有明确推荐地点。"
    return UnifiedBusinessResponse(
        scene="compare",
        summary=summary,
        overall_decision=recommended.overall_decision if recommended else None,
        allow_execute=recommended.allow_cruise if recommended else None,
        risk_reasons=recommended.summary_risk_factors if recommended else [],
        ranked_locations=rankings,
        details={
            "request": response.request,
            "location_count": len(response.comparisons),
            "comparison_mode": response.request.get("comparison_mode"),
        },
    )


def compose_history_response(response: CruiseHistoryResponse) -> UnifiedBusinessResponse:
    """Compose a stable history-scene response."""

    request = response.request
    summary = (
        f"历史任务 {response.request_id} 的整体结论为 {response.advice.overall_decision}，"
        f"地点为 {request.get('location')}。"
    )
    return UnifiedBusinessResponse(
        scene="history",
        summary=summary,
        overall_decision=response.advice.overall_decision,
        allow_execute=response.advice.allow_cruise,
        risk_reasons=response.advice.summary_risk_factors,
        history_summary=ComposedHistorySummary(
            request_id=response.request_id,
            created_at=response.created_at,
            location=_safe_str(request.get("location")),
            task_type=_safe_str(request.get("task_type")),
            date=_safe_str(request.get("date")),
            start_time=_safe_str(request.get("start_time")),
            end_time=_safe_str(request.get("end_time")),
            overall_decision=response.advice.overall_decision,
        ),
        details={
            "hour_count": len(response.advice.hourly_assessment),
            "warning_count": response.warnings.warning_count if response.warnings else 0,
        },
    )


def _build_location_reason(item) -> str | None:
    if not item.available:
        return item.error_message or "地点评估失败"
    if item.best_window:
        return (
            f"最佳窗口 {item.best_window.start_time} 到 {item.best_window.end_time}，"
            f"连续可飞 {item.max_continuous_flyable_hours} 小时。"
        )
    if item.summary_risk_factors:
        return item.summary_risk_factors[0]
    return None


def _safe_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
