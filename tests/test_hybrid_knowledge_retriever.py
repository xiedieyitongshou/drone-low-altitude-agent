from app.schemas.advice import KnowledgeBusinessContext, RetrievedKnowledgeSnippet
from app.services.knowledge_retrievers import HybridKnowledgeRetriever


class FakeKnowledgeStore:
    def __init__(self, results: list[RetrievedKnowledgeSnippet]) -> None:
        self.results = results

    def retrieve(self, query, *, top_k, access_context=None, business_context=None):
        return self.results[:top_k]


def test_hybrid_retriever_merges_sources_and_applies_metadata_boost():
    generic_policy = RetrievedKnowledgeSnippet(
        id="generic-policy",
        title="National high wind policy",
        content="High wind operation advice.",
        score=100.0,
        metadata={
            "retriever": "bm25",
            "task_type": ["inspection"],
            "risk_type": ["high_wind"],
            "province": "National",
            "city": None,
        },
    )
    local_policy = RetrievedKnowledgeSnippet(
        id="local-policy",
        title="Shenzhen high wind policy",
        content="Shenzhen high wind operation advice.",
        score=97.0,
        metadata={
            "retriever": "bm25",
            "task_type": ["inspection"],
            "risk_type": ["high_wind"],
            "province": "Guangdong",
            "city": "Shenzhen",
        },
    )
    bm25_store = FakeKnowledgeStore([generic_policy, local_policy])
    embedding_store = FakeKnowledgeStore(
        [
            generic_policy.model_copy(update={"score": 1.0, "metadata": {**generic_policy.metadata, "retriever": "embedding"}}),
            local_policy.model_copy(update={"score": 0.97, "metadata": {**local_policy.metadata, "retriever": "embedding"}}),
        ]
    )
    retriever = HybridKnowledgeRetriever(bm25_store=bm25_store, embedding_store=embedding_store)

    result = retriever.retrieve(
        "Can I inspect in Shenzhen under high wind?",
        top_k=2,
        business_context=KnowledgeBusinessContext(
            task_type="inspection",
            risk_tags=["high_wind"],
            province="Guangdong",
            city="Shenzhen",
        ),
    )

    assert [item.id for item in result] == ["local-policy", "generic-policy"]
    assert result[0].metadata["retriever"] == "hybrid"
    assert result[0].metadata["retrievers"] == ["bm25", "embedding"]
    assert result[0].metadata["metadata_boost"] == 0.8
    assert result[0].metadata["bm25_score"] == 97.0
    assert result[0].metadata["embedding_score"] == 0.97


def test_hybrid_retriever_keeps_single_source_candidates():
    bm25_only = RetrievedKnowledgeSnippet(
        id="bm25-only",
        title="Exact policy number",
        content="Policy number matched only by keyword.",
        score=10.0,
        metadata={"retriever": "bm25", "task_type": ["inspection"]},
    )
    embedding_only = RetrievedKnowledgeSnippet(
        id="embedding-only",
        title="Semantic policy",
        content="Semantically related policy.",
        score=0.8,
        metadata={"retriever": "embedding", "task_type": ["inspection"]},
    )
    retriever = HybridKnowledgeRetriever(
        bm25_store=FakeKnowledgeStore([bm25_only]),
        embedding_store=FakeKnowledgeStore([embedding_only]),
    )

    result = retriever.retrieve(
        "inspection policy",
        top_k=2,
        business_context=KnowledgeBusinessContext(task_type="inspection"),
    )

    assert {item.id for item in result} == {"bm25-only", "embedding-only"}
    assert next(item for item in result if item.id == "bm25-only").metadata["retrievers"] == ["bm25"]
    assert next(item for item in result if item.id == "embedding-only").metadata["retrievers"] == ["embedding"]
