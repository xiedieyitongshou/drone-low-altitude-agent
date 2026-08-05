from dataclasses import dataclass
import os
from typing import Protocol

from app.schemas.advice import (
    KnowledgeAccessContext,
    KnowledgeBusinessContext,
    RetrievedKnowledgeSnippet,
)
from app.services.bm25_knowledge_store import LocalBm25KnowledgeStore
from app.services.embedding_knowledge_store import LocalEmbeddingKnowledgeStore
from app.services.vector_knowledge_store import LocalVectorKnowledgeStore, build_retrieval_query


HYBRID_BM25_WEIGHT = 0.45
HYBRID_EMBEDDING_WEIGHT = 0.45
HYBRID_METADATA_WEIGHT = 0.10


class KnowledgeRetriever(Protocol):
    name: str

    def retrieve(
        self,
        query: str,
        *,
        top_k: int,
        access_context: KnowledgeAccessContext | None = None,
        business_context: KnowledgeBusinessContext | None = None,
    ) -> list[RetrievedKnowledgeSnippet]:
        ...


@dataclass
class TfidfKnowledgeRetriever:
    store: LocalVectorKnowledgeStore
    name: str = "tfidf"

    def retrieve(
        self,
        query: str,
        *,
        top_k: int,
        access_context: KnowledgeAccessContext | None = None,
        business_context: KnowledgeBusinessContext | None = None,
    ) -> list[RetrievedKnowledgeSnippet]:
        self.store.build_index()
        return self.store.retrieve(
            query,
            top_k=top_k,
            access_context=access_context,
            business_context=business_context,
        )


@dataclass
class Bm25KnowledgeRetriever:
    store: LocalBm25KnowledgeStore
    name: str = "bm25"

    def retrieve(
        self,
        query: str,
        *,
        top_k: int,
        access_context: KnowledgeAccessContext | None = None,
        business_context: KnowledgeBusinessContext | None = None,
    ) -> list[RetrievedKnowledgeSnippet]:
        self.store.build_index()
        return self.store.retrieve(
            query,
            top_k=top_k,
            access_context=access_context,
            business_context=business_context,
        )


@dataclass
class EmbeddingKnowledgeRetriever:
    store: LocalEmbeddingKnowledgeStore
    name: str = "embedding"

    def retrieve(
        self,
        query: str,
        *,
        top_k: int,
        access_context: KnowledgeAccessContext | None = None,
        business_context: KnowledgeBusinessContext | None = None,
    ) -> list[RetrievedKnowledgeSnippet]:
        self.store.build_index()
        return self.store.retrieve(
            query,
            top_k=top_k,
            access_context=access_context,
            business_context=business_context,
        )


@dataclass
class HybridKnowledgeRetriever:
    bm25_store: LocalBm25KnowledgeStore
    embedding_store: LocalEmbeddingKnowledgeStore
    name: str = "hybrid"
    bm25_weight: float = HYBRID_BM25_WEIGHT
    embedding_weight: float = HYBRID_EMBEDDING_WEIGHT
    metadata_weight: float = HYBRID_METADATA_WEIGHT

    def retrieve(
        self,
        query: str,
        *,
        top_k: int,
        access_context: KnowledgeAccessContext | None = None,
        business_context: KnowledgeBusinessContext | None = None,
    ) -> list[RetrievedKnowledgeSnippet]:
        candidate_limit = max(top_k * 3, top_k)
        bm25_results = self.bm25_store.retrieve(
            query,
            top_k=candidate_limit,
            access_context=access_context,
            business_context=business_context,
        )
        embedding_results = self.embedding_store.retrieve(
            query,
            top_k=candidate_limit,
            access_context=access_context,
            business_context=business_context,
        )
        return _merge_hybrid_results(
            bm25_results=bm25_results,
            embedding_results=embedding_results,
            top_k=top_k,
            business_context=business_context,
            bm25_weight=self.bm25_weight,
            embedding_weight=self.embedding_weight,
            metadata_weight=self.metadata_weight,
        )


def create_default_knowledge_retriever() -> KnowledgeRetriever:
    retriever_name = os.getenv("KNOWLEDGE_RETRIEVER", "bm25").strip().lower()
    if retriever_name == "tfidf":
        return TfidfKnowledgeRetriever(store=LocalVectorKnowledgeStore())
    if retriever_name == "bm25":
        return Bm25KnowledgeRetriever(store=LocalBm25KnowledgeStore())
    if retriever_name == "embedding":
        return EmbeddingKnowledgeRetriever(store=LocalEmbeddingKnowledgeStore())
    if retriever_name == "hybrid":
        return HybridKnowledgeRetriever(
            bm25_store=LocalBm25KnowledgeStore(),
            embedding_store=LocalEmbeddingKnowledgeStore(min_score=0.0),
        )
    return TfidfKnowledgeRetriever(store=LocalVectorKnowledgeStore())


def build_knowledge_retrieval_query(
    *,
    task_type: str,
    overall_decision: str | None,
    risk_reasons: list[str],
    warning_types: list[str],
    warning_levels: list[str],
    region: str | None = None,
    province: str | None = None,
    city: str | None = None,
) -> str:
    return build_retrieval_query(
        task_type=task_type,
        overall_decision=overall_decision,
        risk_reasons=risk_reasons,
        warning_types=warning_types,
        warning_levels=warning_levels,
        region=region,
        province=province,
        city=city,
    )


def _merge_hybrid_results(
    *,
    bm25_results: list[RetrievedKnowledgeSnippet],
    embedding_results: list[RetrievedKnowledgeSnippet],
    top_k: int,
    business_context: KnowledgeBusinessContext | None,
    bm25_weight: float,
    embedding_weight: float,
    metadata_weight: float,
) -> list[RetrievedKnowledgeSnippet]:
    bm25_scores = _score_map_by_result_key(bm25_results)
    embedding_scores = _score_map_by_result_key(embedding_results)
    bm25_normalized = _normalize_scores(bm25_scores)
    embedding_normalized = _normalize_scores(embedding_scores)
    merged: dict[str, RetrievedKnowledgeSnippet] = {}
    for item in [*bm25_results, *embedding_results]:
        item_key = _result_key(item)
        if item_key not in merged:
            merged[item_key] = item

    ranked_results: list[RetrievedKnowledgeSnippet] = []
    for item_key, item in merged.items():
        metadata_boost = _metadata_boost(item.metadata, business_context)
        bm25_score = bm25_normalized.get(item_key, 0.0)
        embedding_score = embedding_normalized.get(item_key, 0.0)
        final_score = bm25_score * bm25_weight + embedding_score * embedding_weight + metadata_boost * metadata_weight
        ranked_results.append(
            item.model_copy(
                update={
                    "score": round(final_score, 6),
                    "metadata": {
                        **item.metadata,
                        "retriever": "hybrid",
                        "retrievers": _matched_retrievers(item_key, bm25_scores, embedding_scores),
                        "bm25_score": round(bm25_scores.get(item_key, 0.0), 6),
                        "embedding_score": round(embedding_scores.get(item_key, 0.0), 6),
                        "bm25_score_norm": round(bm25_score, 6),
                        "embedding_score_norm": round(embedding_score, 6),
                        "metadata_boost": round(metadata_boost, 6),
                        "hybrid_weights": {
                            "bm25": bm25_weight,
                            "embedding": embedding_weight,
                            "metadata": metadata_weight,
                        },
                    },
                }
            )
        )

    ranked_results.sort(key=lambda item: (-item.score, item.title))
    return ranked_results[:top_k]


def _score_map_by_result_key(results: list[RetrievedKnowledgeSnippet]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for item in results:
        item_key = _result_key(item)
        scores[item_key] = max(scores.get(item_key, 0.0), item.score)
    return scores


def _result_key(item: RetrievedKnowledgeSnippet) -> str:
    return str(item.metadata.get("chunk_id") or item.id)


def _normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    max_score = max(scores.values(), default=0.0)
    if max_score <= 0:
        return {key: 0.0 for key in scores}
    return {key: value / max_score for key, value in scores.items()}


def _matched_retrievers(
    item_id: str,
    bm25_scores: dict[str, float],
    embedding_scores: dict[str, float],
) -> list[str]:
    retrievers: list[str] = []
    if item_id in bm25_scores:
        retrievers.append("bm25")
    if item_id in embedding_scores:
        retrievers.append("embedding")
    return retrievers


def _metadata_boost(
    metadata: dict[str, object],
    business_context: KnowledgeBusinessContext | None,
) -> float:
    if business_context is None:
        return 0.0

    score = 0.0
    if _same_text(metadata.get("city"), business_context.city):
        score += 0.4
    elif _same_text(metadata.get("province"), business_context.province):
        score += 0.2
    elif _same_text(metadata.get("region"), business_context.region):
        score += 0.1

    if _contains_value(metadata.get("task_type"), business_context.task_type):
        score += 0.2

    if _intersects_values(metadata.get("risk_type"), business_context.risk_tags):
        score += 0.2

    return min(score, 1.0)


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
