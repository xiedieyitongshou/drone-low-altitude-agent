from app.schemas.advice import (
    KnowledgeAccessContext,
    KnowledgeBusinessContext,
    KnowledgeRetrievalRequest,
    RetrievedKnowledgeSnippet,
)
from app.services.advice_retriever import retrieve_knowledge_by_request
from app.services.knowledge_retrievers import build_knowledge_retrieval_query


class FakeKnowledgeRetriever:
    name = "fake"

    def __init__(self) -> None:
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
        return [
            RetrievedKnowledgeSnippet(
                id="fake-1",
                title="深圳巡检知识",
                content="深圳巡检需要关注风速和管制提示。",
                score=0.91,
                metadata={"retriever": self.name},
            )
        ]


def test_retrieve_knowledge_by_request_uses_injected_retriever_and_preserves_context():
    retriever = FakeKnowledgeRetriever()
    request = KnowledgeRetrievalRequest(
        task_type="inspection",
        overall_decision="谨慎飞行",
        risk_reasons=["风速较大"],
        warning_types=["大风"],
        warning_levels=["黄色"],
        region="深圳",
        province="广东",
        city="深圳",
        top_k=3,
    )
    access_context = KnowledgeAccessContext(user_id="user-1", tenant_id="public", role="user")

    response = retrieve_knowledge_by_request(
        request,
        access_context=access_context,
        retriever=retriever,
    )

    assert len(response.snippets) == 1
    assert response.snippets[0].metadata["retriever"] == "fake"
    assert len(retriever.calls) == 1
    call = retriever.calls[0]
    assert call["top_k"] == 3
    assert call["access_context"] == access_context
    assert call["business_context"] == KnowledgeBusinessContext(
        task_type="inspection",
        risk_tags=["high_wind"],
        region="深圳",
        province="广东",
        city="深圳",
    )
    assert "任务类型: inspection" in call["query"]
    assert "风险原因: 风速较大" in call["query"]
    assert "任务地区: 广东 深圳 深圳" in call["query"]


def test_retrieve_knowledge_by_request_prefers_explicit_risk_tags_from_mapper():
    retriever = FakeKnowledgeRetriever()
    request = KnowledgeRetrievalRequest(
        task_type="inspection",
        overall_decision="慎飞",
        risk_reasons=["规则命中但文本不包含可推断关键词"],
        risk_tags=["high_wind", "weather_warning"],
        top_k=3,
    )

    retrieve_knowledge_by_request(request, retriever=retriever)

    assert retriever.calls[0]["business_context"].risk_tags == ["high_wind", "weather_warning"]


def test_build_knowledge_retrieval_query_keeps_existing_query_format():
    query = build_knowledge_retrieval_query(
        task_type="inspection",
        overall_decision="谨慎飞行",
        risk_reasons=["阵风", "降雨"],
        warning_types=["大风"],
        warning_levels=["yellow"],
        province="广东",
        city="深圳",
    )

    assert query == (
        "任务类型: inspection\n"
        "总体结论: 谨慎飞行\n"
        "风险原因: 阵风 降雨\n"
        "预警类型: 大风\n"
        "预警等级: yellow\n"
        "任务地区: 广东 深圳"
    )
