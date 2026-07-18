import json
import os
from functools import lru_cache
from pathlib import Path

from app.schemas.advice import (
    AdviceRetrievalContext,
    AdviceSuggestion,
    KnowledgeAdviceLibrary,
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResponse,
)
from app.services.vector_knowledge_store import LocalVectorKnowledgeStore, build_retrieval_query


DEFAULT_KNOWLEDGE_PATH = Path(os.getenv("ADVICE_KNOWLEDGE_PATH", "data/knowledge/advice_rules.json"))
PRIORITY_SCORE = {"high": 3, "medium": 2, "low": 1}
DECISION_SCOPE_MAP = {
    "适飞": "allow",
    "慎飞": "caution",
    "禁飞": "reject",
}
RISK_TAG_RULES = {
    "high_wind": ["风速", "大风", "风力", "高风"],
    "rainfall": ["雨", "降水", "暴雨", "短时强降水"],
    "thunderstorm": ["雷", "雷暴", "强对流", "雷雨大风"],
    "high_humidity": ["湿度", "高湿"],
    "low_visibility": ["雾", "能见度", "低能见度"],
}
WARNING_LEVEL_MAP = {
    "黄色": "yellow",
    "橙色": "orange",
    "红色": "red",
    "蓝色": "blue",
    "yellow": "yellow",
    "orange": "orange",
    "red": "red",
    "blue": "blue",
}


@lru_cache(maxsize=1)
def load_advice_library(path: str | None = None) -> KnowledgeAdviceLibrary:
    knowledge_path = Path(path) if path else DEFAULT_KNOWLEDGE_PATH
    payload = json.loads(knowledge_path.read_text(encoding="utf-8-sig"))
    return KnowledgeAdviceLibrary.model_validate(payload)


def infer_risk_tags(risk_reasons: list[str]) -> list[str]:
    inferred: list[str] = []
    joined = "\n".join(risk_reasons)
    for risk_tag, keywords in RISK_TAG_RULES.items():
        if any(keyword in joined for keyword in keywords):
            inferred.append(risk_tag)
    return inferred


def normalize_warning_level(level: str | None) -> str | None:
    if not level:
        return None
    return WARNING_LEVEL_MAP.get(level.strip())


def retrieve_advice(context: AdviceRetrievalContext, *, path: str | None = None) -> list[AdviceSuggestion]:
    library = load_advice_library(path)
    decision_scope = DECISION_SCOPE_MAP.get(context.overall_decision or "")
    candidates: list[tuple[int, AdviceSuggestion]] = []

    for item in library.items:
        matched_by: list[str] = []
        score = 0

        if item.task_type and "all" not in item.task_type and context.task_type not in item.task_type:
            continue
        if item.task_type:
            score += 1
            matched_by.append("task_type")

        if decision_scope:
            if item.decision_scope and decision_scope in item.decision_scope:
                score += 3
                matched_by.append("decision_scope")
            elif item.decision_scope:
                continue

        if context.risk_tags:
            overlap_risk = sorted(set(item.risk_type) & set(context.risk_tags))
            if overlap_risk:
                score += 3
                matched_by.append(f"risk_type:{','.join(overlap_risk)}")

        if context.warning_types:
            overlap_warning = sorted(set(item.warning_type) & set(context.warning_types))
            if overlap_warning:
                score += 2
                matched_by.append(f"warning_type:{','.join(overlap_warning)}")

        if context.warning_levels:
            overlap_levels = sorted(set(item.warning_level) & set(context.warning_levels))
            if overlap_levels:
                score += 2
                matched_by.append(f"warning_level:{','.join(overlap_levels)}")

        if not matched_by:
            continue

        score += PRIORITY_SCORE[item.priority.value]
        candidates.append(
            (
                score,
                AdviceSuggestion(
                    id=item.id,
                    title=item.title,
                    advice_text=item.advice_text,
                    priority=item.priority,
                    action_type=item.action_type,
                    source=item.source,
                    source_url=item.source_url,
                    matched_by=matched_by,
                ),
            )
        )

    candidates.sort(key=lambda item: (-item[0], item[1].title))
    return [item[1] for item in candidates[: context.limit]]


def build_advice_context(
    *,
    task_type: str,
    overall_decision: str | None,
    risk_reasons: list[str],
    warning_items: list[dict[str, object]] | None = None,
    limit: int = 5,
) -> AdviceRetrievalContext:
    warning_items = warning_items or []
    warning_types = sorted({str(item.get("event_type")) for item in warning_items if item.get("event_type")})
    warning_levels = sorted(
        {
            level
            for item in warning_items
            for level in [normalize_warning_level(str(item.get("warning_level")) if item.get("warning_level") else None)]
            if level
        }
    )
    return AdviceRetrievalContext(
        task_type=task_type,
        overall_decision=overall_decision,
        risk_tags=infer_risk_tags(risk_reasons),
        warning_types=warning_types,
        warning_levels=warning_levels,
        limit=limit,
    )


def retrieve_knowledge_by_request(payload: KnowledgeRetrievalRequest) -> KnowledgeRetrievalResponse:
    context = AdviceRetrievalContext(
        task_type=payload.task_type,
        overall_decision=payload.overall_decision,
        risk_tags=infer_risk_tags(payload.risk_reasons),
        warning_types=payload.warning_types,
        warning_levels=[level for level in (normalize_warning_level(item) for item in payload.warning_levels) if level],
        limit=payload.top_k,
    )
    advice = retrieve_advice(context)
    vector_store = LocalVectorKnowledgeStore()
    vector_store.build_index()
    query_text = build_retrieval_query(
        task_type=context.task_type,
        overall_decision=context.overall_decision,
        risk_reasons=payload.risk_reasons,
        warning_types=context.warning_types,
        warning_levels=context.warning_levels,
    )
    snippets = vector_store.retrieve(query_text, top_k=payload.top_k)
    return KnowledgeRetrievalResponse(context=context, snippets=snippets, advice=advice)
