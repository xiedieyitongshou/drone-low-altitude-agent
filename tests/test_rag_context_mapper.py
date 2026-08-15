from app.schemas.assessment import CruiseAssessmentAdvice, RiskDecision, RuleHit
from app.services.rag_context_mapper import build_knowledge_request_from_assessment, collect_risk_tags_from_rule_hits


def test_collect_risk_tags_from_rule_hits_deduplicates_non_empty_tags() -> None:
    hits = [
        _rule_hit("wind_speed", "high_wind"),
        _rule_hit("wind_scale", "high_wind"),
        _rule_hit("warning_type", "weather_warning"),
        _rule_hit("humidity", None),
    ]

    assert collect_risk_tags_from_rule_hits(hits) == ["high_wind", "weather_warning"]


def test_build_knowledge_request_from_assessment_maps_rule_hits_to_rag_context() -> None:
    assessment = CruiseAssessmentAdvice(
        allow_cruise=False,
        overall_decision=RiskDecision.PROHIBITED,
        summary_risk_factors=["2026-08-15T10:00:00+08:00 风险较高：风速偏高"],
        rule_hits=[
            _rule_hit("wind_speed", "high_wind"),
            _rule_hit("warning_type", "weather_warning"),
        ],
        hourly_assessment=[],
    )

    request = build_knowledge_request_from_assessment(
        task_type="inspection",
        assessment=assessment,
        warning_items=[{"event_type": "大风", "warning_level": "yellow"}],
        province="广东",
        city="深圳",
        top_k=5,
    )

    assert request.task_type == "inspection"
    assert request.overall_decision == RiskDecision.PROHIBITED.value
    assert request.risk_tags == ["high_wind", "weather_warning"]
    assert request.warning_types == ["大风"]
    assert request.warning_levels == ["yellow"]
    assert request.province == "广东"
    assert request.city == "深圳"
    assert request.top_k == 5


def _rule_hit(metric: str, risk_tag: str | None) -> RuleHit:
    return RuleHit(
        metric=metric,
        operator=">=",
        actual_value=30,
        threshold=25,
        decision=RiskDecision.PROHIBITED,
        label="规则命中",
        risk_tag=risk_tag,
    )
