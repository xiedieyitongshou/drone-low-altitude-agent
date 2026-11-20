import json
import os
import pickle
from functools import lru_cache
from pathlib import Path

from app.schemas.advice import (
    AdviceRetrievalContext,
    AdviceSuggestion,
    KnowledgeAccessContext,
    KnowledgeAdviceLibrary,
    KnowledgeBusinessContext,
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResponse,
    KnowledgeType,
)
from app.services.knowledge_retrievers import (
    KnowledgeRetriever,
    build_knowledge_retrieval_query,
    create_default_knowledge_retriever,
)
from app.services.knowledge_reranker import assess_candidate_relevance
from app.services.vector_knowledge_store import (
    document_rejection_reasons,
    get_default_knowledge_path,
    is_document_visible,
)
from app.services.rag_fallback import (
    build_rag_fallback_message,
    evaluate_rag_confidence,
    rewrite_rag_query,
)


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
    knowledge_path = Path(path) if path else get_default_knowledge_path()
    payload = json.loads(knowledge_path.read_text(encoding="utf-8-sig"))
    return KnowledgeAdviceLibrary.model_validate(payload)


def infer_risk_tags(risk_reasons: list[str]) -> list[str]:
    inferred: list[str] = []
    joined = "\n".join(risk_reasons)
    for risk_tag, keywords in RISK_TAG_RULES.items():
        if any(keyword in joined for keyword in keywords):
            inferred.append(risk_tag)
    return inferred


def merge_risk_tags(*tag_groups: list[str]) -> list[str]:
    merged: list[str] = []
    for tags in tag_groups:
        for tag in tags:
            normalized = str(tag).strip()
            if normalized and normalized not in merged:
                merged.append(normalized)
    return merged


def normalize_warning_level(level: str | None) -> str | None:
    if not level:
        return None
    return WARNING_LEVEL_MAP.get(level.strip())


def retrieve_advice(
    context: AdviceRetrievalContext, *, path: str | None = None,
    business_context: KnowledgeBusinessContext | None = None, access_context: KnowledgeAccessContext | None = None,
) -> list[AdviceSuggestion]:
    library = load_advice_library(path)
    decision_scope = DECISION_SCOPE_MAP.get(context.overall_decision or "")
    candidates: list[tuple[int, AdviceSuggestion]] = []
    business_context = business_context or KnowledgeBusinessContext(
        task_type=context.task_type, risk_tags=context.risk_tags, overall_decision=context.overall_decision,
        warning_types=context.warning_types if context.overall_decision else None,
        warning_levels=context.warning_levels if context.overall_decision else None,
    )

    for item in library.items:
        if item.knowledge_type == KnowledgeType.POLICY_HINT:
            continue
        metadata = item.model_dump(mode="json")
        if not is_document_visible(metadata, access_context) or document_rejection_reasons(metadata, business_context):
            continue

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


def retrieve_knowledge_by_request(
    payload: KnowledgeRetrievalRequest,
    *,
    access_context: KnowledgeAccessContext | None = None,
    retriever: KnowledgeRetriever | None = None,
) -> KnowledgeRetrievalResponse:
    context = AdviceRetrievalContext(
        task_type=payload.task_type,
        overall_decision=payload.overall_decision,
        risk_tags=merge_risk_tags(payload.risk_tags, infer_risk_tags(payload.risk_reasons)),
        warning_types=payload.warning_types or [],
        warning_levels=[level for level in (normalize_warning_level(item) for item in payload.warning_levels or []) if level],
        limit=payload.top_k,
    )
    business_context = KnowledgeBusinessContext(
        task_type=context.task_type,
        risk_tags=context.risk_tags,
        region=payload.region,
        province=payload.province,
        city=payload.city,
        as_of=payload.as_of,
        overall_decision=payload.overall_decision,
        warning_types=payload.warning_types,
        warning_levels=context.warning_levels if payload.warning_levels is not None else None,
    )
    advice: list[AdviceSuggestion] = []
    retrieval_metadata: dict[str, object] = {
        "query_rewritten": False, "attempts": [], "reason_code": None,
        "constraint_sources": payload.constraint_sources,
    }
    missing_fields = [field for field in payload.required_context_fields if field in {"city", "as_of"} and not getattr(payload, field)]
    if missing_fields:
        retrieval_metadata.update(reason_code="clarification_required", missing_fields=missing_fields)
        return KnowledgeRetrievalResponse(
            context=context, retrieval_status="fallback", retrieval_metadata=retrieval_metadata,
            retrieval_message="请补充查询所需的地区或适用日期。",
        )
    query_text = build_knowledge_retrieval_query(
        task_type=context.task_type,
        overall_decision=context.overall_decision,
        risk_reasons=payload.risk_reasons,
        warning_types=context.warning_types,
        warning_levels=context.warning_levels,
        region=payload.region,
        province=payload.province,
        city=payload.city,
        query=payload.query,
    )
    try:
        active_retriever = retriever or create_default_knowledge_retriever()
        retrieval_metadata["retriever"] = active_retriever.name
        if not payload.query:
            advice = retrieve_advice(context, business_context=business_context, access_context=access_context)
        candidate_limit = max(10, payload.top_k * 3)
        retrieval_metadata["candidate_limit"] = candidate_limit
        for attempt in (1, 2):
            business_context.rejection_counts.clear()
            business_context.rejected_candidates.clear()
            snippets = active_retriever.retrieve(
                query_text, top_k=candidate_limit, access_context=access_context, business_context=business_context,
            )
            decision = evaluate_rag_confidence(snippets)
            accepted = []
            rejections = list(business_context.rejected_candidates)
            for snippet in snippets:
                if not is_document_visible(snippet.metadata, access_context):
                    continue
                reasons = document_rejection_reasons(snippet.metadata, business_context)
                if not evaluate_rag_confidence([snippet]).is_confident:
                    reasons.append("low_score")
                if reasons:
                    rejections.append({"id": str(snippet.metadata.get("chunk_id") or snippet.id), "reasons": reasons})
                else:
                    accepted.append(snippet)
            review_status = "not_needed"
            if payload.query:
                accepted, irrelevant, review_status = assess_candidate_relevance(payload.query, accepted, business_context)
                rejections.extend(irrelevant)
            reason = "accepted" if accepted else "no_candidates"
            status = "success" if accepted else decision.status
            if snippets and not accepted and decision.is_confident:
                reason, status = "insufficient_relevance", "no_answer"
            elif snippets and not decision.is_confident:
                reason = "low_confidence"
            elif business_context.rejection_counts:
                reason = "no_applicable_knowledge"
            retrieval_metadata["reason_code"] = reason
            retrieval_metadata["attempts"].append({
                "attempt": attempt, "query": query_text, "status": status, "reason": reason,
                "top_score": decision.top_score, "result_count": len(accepted), "threshold": decision.threshold,
                "candidate_count": len(snippets), "rejected_candidates": rejections,
                "filter_counts": dict(business_context.rejection_counts), "llm_review_status": review_status,
            })
            if accepted:
                return KnowledgeRetrievalResponse(
                    context=context, advice=advice,
                    snippets=_mark_rag_attempt(accepted[:payload.top_k], attempt=attempt, query_rewritten=attempt == 2),
                    retrieval_status="success" if attempt == 1 else "rewritten_success",
                    retrieval_metadata=retrieval_metadata,
                )
            if attempt == 1:
                query_text = rewrite_rag_query(
                    query_text, business_context=business_context, risk_reasons=payload.risk_reasons,
                    warning_types=context.warning_types, warning_levels=context.warning_levels,
                )
                retrieval_metadata.update(query_rewritten=True, rewrite_query=query_text)
    except (OSError, ValueError, TypeError, RuntimeError, EOFError, pickle.UnpicklingError) as exc:
        retrieval_metadata.update(reason_code="retrieval_error", error_type=type(exc).__name__)
        return KnowledgeRetrievalResponse(
            context=context, advice=advice, retrieval_status="error", retrieval_metadata=retrieval_metadata,
            retrieval_message="知识检索暂时不可用，请稍后重试。",
        )
    return KnowledgeRetrievalResponse(
        context=context,
        snippets=[],
        advice=advice,
        retrieval_status="fallback",
        retrieval_message=(build_rag_fallback_message(decision) if retrieval_metadata["reason_code"] == "low_confidence"
                           else "当前知识库没有找到足以回答本次问题的适用依据，请补充具体对象或查询条件。"),
        retrieval_metadata=retrieval_metadata,
    )


def _mark_rag_attempt(
    snippets: list,
    *,
    attempt: int,
    query_rewritten: bool,
) -> list:
    return [
        snippet.model_copy(
            update={
                "metadata": {
                    **snippet.metadata,
                    "rag_attempt": attempt,
                    "query_rewritten": query_rewritten,
                }
            }
        )
        for snippet in snippets
    ]
