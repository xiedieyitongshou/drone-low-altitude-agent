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
from app.services.advice_retriever import build_advice_context, retrieve_advice, retrieve_knowledge_by_request
from app.services.response_explainer import explain_business_response


def compose_evaluation_response(response: CruiseAssessmentResponse) -> UnifiedBusinessResponse:
    """Compose a stable evaluate-scene response for frontend and later LLM use."""

    request = response.request
    summary = (
        f"{request.get('location')} {request.get('date')} "
        f"{request.get('start_time')}-{request.get('end_time')} "
        f"任务结论为 {response.advice.overall_decision}。"
    )
    warning_items = [item.model_dump() for item in response.warnings.warnings] if response.warnings else []
    advice_context = build_advice_context(
        task_type=str(request.get('task_type') or 'cruise'),
        overall_decision=str(response.advice.overall_decision),
        risk_reasons=response.advice.summary_risk_factors,
        warning_items=warning_items,
        limit=3,
    )
    advice = [item.model_dump(mode='json') for item in retrieve_advice(advice_context)]
    knowledge = retrieve_knowledge_by_request(
        payload=_build_knowledge_request(
            task_type=str(request.get('task_type') or 'cruise'),
            overall_decision=str(response.advice.overall_decision),
            risk_reasons=response.advice.summary_risk_factors,
            warning_items=warning_items,
            top_k=3,
        )
    )
    return _with_explanation(UnifiedBusinessResponse(
        scene="evaluate",
        summary=summary,
        overall_decision=response.advice.overall_decision,
        allow_execute=response.advice.allow_cruise,
        risk_reasons=response.advice.summary_risk_factors,
        details={
            "request": response.request,
            "warning_count": response.warnings.warning_count if response.warnings else 0,
            "hour_count": len(response.advice.hourly_assessment),
            "advice": advice,
            "knowledge_snippets": [item.model_dump(mode='json') for item in knowledge.snippets],
        },
    ))


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

    warning_items = [item.model_dump() for item in response.warnings.warnings] if response.warnings else []
    knowledge = retrieve_knowledge_by_request(
        payload=_build_knowledge_request(
            task_type=str(response.request.get('task_type') or 'cruise'),
            overall_decision=str(overall_decision) if overall_decision else None,
            risk_reasons=risk_reasons,
            warning_items=warning_items,
            top_k=3,
        )
    )

    return _with_explanation(UnifiedBusinessResponse(
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
            "advice": [item.model_dump(mode='json') for item in knowledge.advice],
            "knowledge_snippets": [item.model_dump(mode='json') for item in knowledge.snippets],
        },
    ))


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
    risk_reasons = recommended.summary_risk_factors if recommended else []
    knowledge = retrieve_knowledge_by_request(
        payload=_build_knowledge_request(
            task_type=str(response.request.get('task_type') or 'cruise'),
            overall_decision=str(recommended.overall_decision) if recommended and recommended.overall_decision else None,
            risk_reasons=risk_reasons,
            warning_items=[],
            top_k=3,
        )
    )
    return _with_explanation(UnifiedBusinessResponse(
        scene="compare",
        summary=summary,
        overall_decision=recommended.overall_decision if recommended else None,
        allow_execute=recommended.allow_cruise if recommended else None,
        risk_reasons=risk_reasons,
        ranked_locations=rankings,
        details={
            "request": response.request,
            "location_count": len(response.comparisons),
            "comparison_mode": response.request.get("comparison_mode"),
            "advice": [item.model_dump(mode='json') for item in knowledge.advice],
            "knowledge_snippets": [item.model_dump(mode='json') for item in knowledge.snippets],
        },
    ))


def compose_history_response(response: CruiseHistoryResponse) -> UnifiedBusinessResponse:
    """Compose a stable history-scene response."""

    request = response.request
    summary = (
        f"历史任务 {response.request_id} 的整体结论为 {response.advice.overall_decision}，"
        f"地点为 {request.get('location')}。"
    )
    warning_items = [item.model_dump() for item in response.warnings.warnings] if response.warnings else []
    knowledge = retrieve_knowledge_by_request(
        payload=_build_knowledge_request(
            task_type=str(request.get('task_type') or 'cruise'),
            overall_decision=str(response.advice.overall_decision),
            risk_reasons=response.advice.summary_risk_factors,
            warning_items=warning_items,
            top_k=3,
        )
    )
    return _with_explanation(UnifiedBusinessResponse(
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
            "advice": [item.model_dump(mode='json') for item in knowledge.advice],
            "knowledge_snippets": [item.model_dump(mode='json') for item in knowledge.snippets],
        },
    ))


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


def _with_explanation(response: UnifiedBusinessResponse) -> UnifiedBusinessResponse:
    explanation = explain_business_response(response)
    response.explanation = explanation.text
    response.explanation_source = explanation.source
    response.llm_used = explanation.llm_used
    return response


def _build_knowledge_request(*, task_type: str, overall_decision: str | None, risk_reasons: list[str], warning_items: list[dict[str, object]], top_k: int):
    from app.schemas import KnowledgeRetrievalRequest

    warning_types = [str(item.get('event_type')) for item in warning_items if item.get('event_type')]
    warning_levels = [str(item.get('warning_level')) for item in warning_items if item.get('warning_level')]
    return KnowledgeRetrievalRequest(
        task_type=task_type,
        overall_decision=overall_decision,
        risk_reasons=risk_reasons,
        warning_types=warning_types,
        warning_levels=warning_levels,
        top_k=top_k,
    )
