from app.schemas.advice import (
    KnowledgeAccessContext,
    KnowledgeBusinessContext,
    KnowledgeRetrievalRequest,
    RetrievedKnowledgeSnippet,
)
from app.services.advice_retriever import retrieve_knowledge_by_request
from app.services.rag_fallback import evaluate_rag_confidence, rewrite_rag_query


class SequenceKnowledgeRetriever:
    name = "sequence"

    def __init__(self, results_by_call: list[list[RetrievedKnowledgeSnippet]]) -> None:
        self.results_by_call = results_by_call
        self.calls = []

    def retrieve(
        self,
        query: str,
        *,
        top_k: int,
        access_context: KnowledgeAccessContext | None = None,
        business_context: KnowledgeBusinessContext | None = None,
    ) -> list[RetrievedKnowledgeSnippet]:
        self.calls.append(
            {
                "query": query,
                "top_k": top_k,
                "access_context": access_context,
                "business_context": business_context,
            }
        )
        index = min(len(self.calls) - 1, len(self.results_by_call) - 1)
        return self.results_by_call[index]


def test_evaluate_rag_confidence_distinguishes_empty_low_and_success():
    assert evaluate_rag_confidence([], threshold=0.2).status == "empty"
    assert (
        evaluate_rag_confidence(
            [RetrievedKnowledgeSnippet(id="weak", title="weak", content="weak", score=0.1)],
            threshold=0.2,
        ).status
        == "low_confidence"
    )
    assert (
        evaluate_rag_confidence(
            [RetrievedKnowledgeSnippet(id="ok", title="ok", content="ok", score=0.8)],
            threshold=0.2,
        ).status
        == "success"
    )


def test_rewrite_rag_query_adds_business_context():
    query = rewrite_rag_query(
        "original",
        business_context=KnowledgeBusinessContext(
            task_type="inspection",
            risk_tags=["high_wind"],
            province="Guangdong",
            city="Shenzhen",
        ),
        risk_reasons=["strong wind"],
        warning_types=["wind"],
        warning_levels=["yellow"],
    )

    assert "original" in query
    assert "补充检索上下文" in query
    assert "inspection" in query
    assert "high_wind" in query
    assert "Guangdong Shenzhen" in query


def test_retrieve_knowledge_by_request_rewrites_query_for_empty_first_recall():
    retriever = SequenceKnowledgeRetriever(
        [
            [],
            [
                RetrievedKnowledgeSnippet(
                    id="policy-1",
                    title="policy",
                    content="policy content",
                    score=0.8,
                    metadata={"retriever": "hybrid"},
                )
            ],
        ]
    )
    request = KnowledgeRetrievalRequest(
        task_type="inspection",
        risk_reasons=["strong wind"],
        warning_types=["wind"],
        warning_levels=["yellow"],
        province="Guangdong",
        city="Shenzhen",
        top_k=3,
    )

    response = retrieve_knowledge_by_request(request, retriever=retriever)

    assert response.retrieval_status == "rewritten_success"
    assert response.retrieval_metadata["query_rewritten"] is True
    assert len(retriever.calls) == 2
    assert "补充检索上下文" in retriever.calls[1]["query"]
    assert response.snippets[0].metadata["rag_attempt"] == 2
    assert response.snippets[0].metadata["query_rewritten"] is True


def test_retrieve_knowledge_by_request_returns_fallback_after_low_confidence_retry():
    low_confidence = RetrievedKnowledgeSnippet(
        id="weak-1",
        title="weak",
        content="weak content",
        score=0.01,
        metadata={"retriever": "hybrid"},
    )
    retriever = SequenceKnowledgeRetriever([[low_confidence], [low_confidence]])
    request = KnowledgeRetrievalRequest(
        task_type="inspection",
        risk_reasons=["unknown"],
        province="Guangdong",
        city="Shenzhen",
        top_k=3,
    )

    response = retrieve_knowledge_by_request(request, retriever=retriever)

    assert response.retrieval_status == "fallback"
    assert response.snippets == []
    assert response.retrieval_message is not None
    assert "置信度较低" in response.retrieval_message
    assert len(response.retrieval_metadata["attempts"]) == 2
    assert response.retrieval_metadata["attempts"][0]["status"] == "low_confidence"
    assert response.retrieval_metadata["attempts"][1]["status"] == "low_confidence"
