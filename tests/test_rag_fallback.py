import json
import pickle

import pytest

from app.schemas.advice import (
    KnowledgeAccessContext,
    KnowledgeBusinessContext,
    KnowledgeRetrievalRequest,
    RetrievedKnowledgeSnippet,
)
from app.services.advice_retriever import retrieve_knowledge_by_request
from app.services.rag_fallback import evaluate_rag_confidence, rewrite_rag_query
from app.services.knowledge_reranker import assess_candidate_relevance


def test_each_candidate_requires_its_own_score_and_relevance(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "false")
    results = [
        RetrievedKnowledgeSnippet(id="irrelevant", title="飞行预警", content="橙色预警建议取消任务", score=20, metadata={"review_status": "approved"}),
        RetrievedKnowledgeSnippet(id="weak", title="电池寿命", content="电池寿命为300次", score=0.01, metadata={"review_status": "approved"}),
        RetrievedKnowledgeSnippet(id="answer", title="电池寿命", content="电池寿命为300次", score=3, metadata={"review_status": "approved"}),
    ]
    retriever = SequenceKnowledgeRetriever([results])
    response = retrieve_knowledge_by_request(KnowledgeRetrievalRequest(task_type="cruise", query="电池寿命", top_k=1), retriever=retriever)

    assert [item.id for item in response.snippets] == ["answer"]
    assert retriever.calls[0]["top_k"] == 10
    rejections = response.retrieval_metadata["attempts"][0]["rejected_candidates"]
    assert any(item["id"] == "weak" and "low_score" in item["reasons"] for item in rejections)
    assert any(item["id"] == "irrelevant" and item["reason"] == "no_topic_match" for item in rejections)


def test_rewrite_cannot_turn_an_unsupported_subject_into_an_answer(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "false")
    irrelevant = RetrievedKnowledgeSnippet(id="general", title="电池检查", content="飞行前检查电池", score=20, metadata={"review_status": "approved"})
    retriever = SequenceKnowledgeRetriever([[irrelevant], [irrelevant]])
    response = retrieve_knowledge_by_request(KnowledgeRetrievalRequest(task_type="cruise", query="ZXQ734电池循环寿命"), retriever=retriever)
    assert response.retrieval_status == "fallback"
    assert response.snippets == response.advice == []
    assert len(retriever.calls) == 2
    assert all(attempt["rejected_candidates"][0]["reason"] == "subject_not_supported" for attempt in response.retrieval_metadata["attempts"])


def test_index_corruption_is_reported_as_a_retrieval_error():
    class BrokenRetriever:
        name = "broken"

        def retrieve(self, *args, **kwargs):
            raise pickle.UnpicklingError("index damaged")

    response = retrieve_knowledge_by_request(KnowledgeRetrievalRequest(task_type="cruise", query="报备政策"), retriever=BrokenRetriever())
    assert response.retrieval_status == "error"
    assert response.retrieval_metadata["reason_code"] == "retrieval_error"
    assert response.snippets == []


@pytest.mark.parametrize("review", [None, "not JSON", '{"judgements":[{"id":"partial","relevant":true,"evidence":"invented"}]}'])
def test_failed_or_unsupported_llm_review_retains_uncertain_candidates_as_rejected(monkeypatch, review):
    monkeypatch.setattr("app.services.knowledge_reranker.is_llm_enabled", lambda: True)
    monkeypatch.setattr("app.services.knowledge_reranker.generate_text", lambda **kwargs: review)
    snippet = RetrievedKnowledgeSnippet(id="partial", title="电池", content="电池检查", score=3)
    accepted, rejected, _ = assess_candidate_relevance("电池寿命", [snippet], KnowledgeBusinessContext())
    assert accepted == []
    assert rejected[0]["reason"] == "insufficient_relevance"


def test_llm_review_requires_a_quote_from_the_candidate(monkeypatch):
    monkeypatch.setattr("app.services.knowledge_reranker.is_llm_enabled", lambda: True)
    monkeypatch.setattr("app.services.knowledge_reranker.generate_text", lambda **kwargs: json.dumps({"judgements": [
        {"id": "partial", "relevant": True, "evidence": "300次"}
    ]}))
    snippet = RetrievedKnowledgeSnippet(id="partial", title="电池", content="电池可充放300次后更换", score=3)
    accepted, _, status = assess_candidate_relevance("电池寿命", [snippet], KnowledgeBusinessContext())
    assert status == "completed"
    assert accepted[0].metadata["relevance_method"] == "llm"


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


@pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_scores_are_rejected_even_when_the_threshold_is_zero(score):
    snippet = RetrievedKnowledgeSnippet(id="invalid", title="invalid", content="invalid", score=score)
    decision = evaluate_rag_confidence([snippet], threshold=0)
    assert decision.is_confident is False
    assert decision.reason == "non_finite_score"


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
    assert "strong wind" in query
    assert "wind" in query
    assert "yellow" in query


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
                    metadata={"retriever": "hybrid", "review_status": "approved"},
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
    assert "strong wind" in retriever.calls[1]["query"]
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
