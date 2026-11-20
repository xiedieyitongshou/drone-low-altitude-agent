import os
import math
from dataclasses import dataclass

from app.schemas.advice import KnowledgeBusinessContext, RetrievedKnowledgeSnippet


DEFAULT_RAG_CONFIDENCE_THRESHOLD = 0.2


@dataclass(frozen=True)
class RagConfidenceDecision:
    is_confident: bool
    status: str
    reason: str
    top_score: float
    result_count: int
    threshold: float


def load_rag_confidence_threshold() -> float:
    raw_value = os.getenv("RAG_CONFIDENCE_THRESHOLD")
    if raw_value is None:
        return DEFAULT_RAG_CONFIDENCE_THRESHOLD
    try:
        threshold = float(raw_value)
        return threshold if math.isfinite(threshold) and threshold >= 0 else DEFAULT_RAG_CONFIDENCE_THRESHOLD
    except ValueError:
        return DEFAULT_RAG_CONFIDENCE_THRESHOLD


def evaluate_rag_confidence(
    snippets: list[RetrievedKnowledgeSnippet],
    *,
    threshold: float | None = None,
) -> RagConfidenceDecision:
    active_threshold = threshold if threshold is not None else load_rag_confidence_threshold()
    if not snippets:
        return RagConfidenceDecision(
            is_confident=False,
            status="empty",
            reason="no_snippets_retrieved",
            top_score=0.0,
            result_count=0,
            threshold=active_threshold,
        )

    finite_scores = [snippet.score for snippet in snippets if math.isfinite(snippet.score)]
    top_score = max(finite_scores, default=0.0)
    if not finite_scores or top_score < active_threshold:
        return RagConfidenceDecision(
            is_confident=False,
            status="low_confidence",
            reason="top_score_below_threshold" if finite_scores else "non_finite_score",
            top_score=top_score,
            result_count=len(snippets),
            threshold=active_threshold,
        )

    return RagConfidenceDecision(
        is_confident=True,
        status="success",
        reason="top_score_meets_threshold",
        top_score=top_score,
        result_count=len(snippets),
        threshold=active_threshold,
    )


def rewrite_rag_query(
    original_query: str,
    *,
    business_context: KnowledgeBusinessContext,
    risk_reasons: list[str],
    warning_types: list[str],
    warning_levels: list[str],
) -> str:
    from app.services.embedding_providers import SEMANTIC_EXPANSIONS

    synonyms = [alias for term, aliases in SEMANTIC_EXPANSIONS.items() if term in original_query for alias in aliases]
    return " ".join(dict.fromkeys([original_query, *synonyms, *risk_reasons, *warning_types, *warning_levels]))


def build_rag_fallback_message(decision: RagConfidenceDecision) -> str:
    if decision.status == "empty":
        return "当前知识库没有召回到可用依据，建议补充地区、任务类型、风险原因或相关政策关键词后再查询。"
    return "当前知识库召回结果置信度较低，暂不把低置信内容作为依据，建议补充更明确的业务场景后再查询。"
