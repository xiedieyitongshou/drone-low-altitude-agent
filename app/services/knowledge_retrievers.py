from dataclasses import dataclass
import os
from typing import Protocol

from app.schemas.advice import (
    KnowledgeAccessContext,
    KnowledgeBusinessContext,
    RetrievedKnowledgeSnippet,
)
from app.services.bm25_knowledge_store import LocalBm25KnowledgeStore
from app.services.vector_knowledge_store import LocalVectorKnowledgeStore, build_retrieval_query


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


def create_default_knowledge_retriever() -> KnowledgeRetriever:
    retriever_name = os.getenv("KNOWLEDGE_RETRIEVER", "bm25").strip().lower()
    if retriever_name == "tfidf":
        return TfidfKnowledgeRetriever(store=LocalVectorKnowledgeStore())
    if retriever_name == "bm25":
        return Bm25KnowledgeRetriever(store=LocalBm25KnowledgeStore())
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
