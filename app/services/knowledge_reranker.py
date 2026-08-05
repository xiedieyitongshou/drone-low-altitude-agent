from app.schemas.advice import KnowledgeBusinessContext


def rule_rerank_boost(
    metadata: dict[str, object],
    business_context: KnowledgeBusinessContext | None,
) -> float:
    score = 0.0
    if metadata.get("review_status") == "approved":
        score += 0.2
    if metadata.get("expires_at") in (None, ""):
        score += 0.1
    score += _knowledge_type_priority(metadata.get("knowledge_type")) * 0.2

    if business_context is not None:
        if _same_text(metadata.get("city"), business_context.city):
            score += 0.3
        elif _same_text(metadata.get("province"), business_context.province):
            score += 0.2
        elif _same_text(metadata.get("region"), business_context.region):
            score += 0.1
        if _contains_value(metadata.get("task_type"), business_context.task_type):
            score += 0.1
        if _intersects_values(metadata.get("risk_type"), business_context.risk_tags):
            score += 0.1

    return min(score, 1.0)


def _knowledge_type_priority(value: object) -> float:
    return {
        "policy_hint": 1.0,
        "sop": 0.85,
        "risk_advice": 0.7,
        "faq": 0.55,
    }.get(str(value), 0.4)


def _same_text(left: object, right: str | None) -> bool:
    if left in (None, "") or right in (None, ""):
        return False
    return str(left).strip() == str(right).strip()


def _contains_value(values: object, expected: str | None) -> bool:
    if expected in (None, ""):
        return False
    return str(expected) in _to_string_set(values)


def _intersects_values(values: object, expected_values: list[str]) -> bool:
    if not expected_values:
        return False
    return bool(_to_string_set(values) & {str(value) for value in expected_values})


def _to_string_set(values: object) -> set[str]:
    if values is None:
        return set()
    if isinstance(values, list):
        return {str(value) for value in values if value not in (None, "")}
    return {str(values)}
