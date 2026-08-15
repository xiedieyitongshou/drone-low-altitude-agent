from app.schemas import KnowledgeRetrievalRequest
from app.schemas.assessment import CruiseAssessmentAdvice, RuleHit


def build_knowledge_request_from_assessment(
    *,
    task_type: str,
    assessment: CruiseAssessmentAdvice,
    warning_items: list[dict[str, object]] | None = None,
    region: str | None = None,
    province: str | None = None,
    city: str | None = None,
    top_k: int = 3,
) -> KnowledgeRetrievalRequest:
    return build_knowledge_request_from_rule_context(
        task_type=task_type,
        overall_decision=str(assessment.overall_decision),
        risk_reasons=list(assessment.summary_risk_factors),
        rule_hits=list(assessment.rule_hits),
        warning_items=warning_items or [],
        region=region,
        province=province,
        city=city,
        top_k=top_k,
    )


def build_knowledge_request_from_rule_context(
    *,
    task_type: str,
    overall_decision: str | None,
    risk_reasons: list[str],
    rule_hits: list[RuleHit] | None = None,
    warning_items: list[dict[str, object]] | None = None,
    region: str | None = None,
    province: str | None = None,
    city: str | None = None,
    top_k: int = 3,
) -> KnowledgeRetrievalRequest:
    warning_items = warning_items or []
    return KnowledgeRetrievalRequest(
        task_type=task_type,
        overall_decision=overall_decision,
        risk_reasons=list(risk_reasons),
        risk_tags=collect_risk_tags_from_rule_hits(rule_hits or []),
        warning_types=[str(item.get("event_type")) for item in warning_items if item.get("event_type")],
        warning_levels=[str(item.get("warning_level")) for item in warning_items if item.get("warning_level")],
        region=region,
        province=province,
        city=city,
        top_k=top_k,
    )


def collect_risk_tags_from_rule_hits(rule_hits: list[RuleHit]) -> list[str]:
    tags: list[str] = []
    for hit in rule_hits:
        tag = (hit.risk_tag or "").strip()
        if tag and tag not in tags:
            tags.append(tag)
    return tags
