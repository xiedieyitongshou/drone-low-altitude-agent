from app.schemas.advice import KnowledgeAdviceLibrary
from app.services.knowledge_chunker import build_indexed_chunks
from app.services.knowledge_reranker import rule_rerank_boost


def test_build_indexed_chunks_uses_strategy_by_knowledge_type():
    library = KnowledgeAdviceLibrary.model_validate(
        {
            "version": "v1",
            "items": [
                _knowledge_item(
                    item_id="policy-1",
                    knowledge_type="policy_hint",
                    advice_text="Article 1: Register before flight.\n\nArticle 2: Check restricted airspace.",
                ),
                _knowledge_item(
                    item_id="sop-1",
                    knowledge_type="sop",
                    advice_text="Step 1: Check battery.\nStep 2: Confirm weather.",
                ),
                _knowledge_item(
                    item_id="faq-1",
                    knowledge_type="faq",
                    advice_text="Q: Can I fly today?\nA: Check risk first.\nQ: Need approval?\nA: Follow local policy.",
                ),
                _knowledge_item(
                    item_id="risk-1",
                    knowledge_type="risk_advice",
                    advice_text="Avoid flight under strong wind.",
                ),
            ],
        }
    )

    chunks = build_indexed_chunks(library)

    assert [chunk.chunk_type for chunk in chunks if chunk.knowledge_id == "policy-1"] == [
        "policy_clause",
        "policy_clause",
    ]
    assert [chunk.chunk_type for chunk in chunks if chunk.knowledge_id == "sop-1"] == ["sop_step", "sop_step"]
    assert [chunk.chunk_type for chunk in chunks if chunk.knowledge_id == "faq-1"] == ["qa_pair", "qa_pair"]
    assert [chunk.chunk_type for chunk in chunks if chunk.knowledge_id == "risk-1"] == ["risk_block"]
    assert chunks[0].metadata["chunk_id"] == chunks[0].id
    assert chunks[0].metadata["knowledge_id"] == "policy-1"


def test_rule_rerank_boost_prefers_precise_business_match():
    generic_score = rule_rerank_boost(
        {
            "knowledge_type": "faq",
            "review_status": "approved",
            "expires_at": None,
            "task_type": ["inspection"],
            "risk_type": ["high_wind"],
            "province": "National",
        },
        None,
    )
    local_score = rule_rerank_boost(
        {
            "knowledge_type": "policy_hint",
            "review_status": "approved",
            "expires_at": None,
            "task_type": ["inspection"],
            "risk_type": ["high_wind"],
            "province": "Guangdong",
            "city": "Shenzhen",
        },
        _business_context(),
    )

    assert local_score > generic_score


def _knowledge_item(*, item_id: str, knowledge_type: str, advice_text: str):
    return {
        "id": item_id,
        "category": "risk_advice",
        "knowledge_type": knowledge_type,
        "risk_type": ["high_wind"],
        "task_type": ["inspection"],
        "warning_type": [],
        "warning_level": [],
        "decision_scope": [],
        "region": None,
        "province": "Guangdong",
        "city": "Shenzhen",
        "visibility": "public",
        "tenant_id": "public",
        "user_id": None,
        "version": "v1",
        "effective_at": None,
        "expires_at": None,
        "review_status": "approved",
        "title": f"{item_id} title",
        "advice_text": advice_text,
        "priority": "high",
        "action_type": "reduce_risk",
        "keywords": ["inspection", "high_wind"],
        "source": "local sample",
        "source_url": None,
        "notes": None,
    }


def _business_context():
    from app.schemas.advice import KnowledgeBusinessContext

    return KnowledgeBusinessContext(
        task_type="inspection",
        risk_tags=["high_wind"],
        province="Guangdong",
        city="Shenzhen",
    )
