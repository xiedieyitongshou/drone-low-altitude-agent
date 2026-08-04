import json

from app.schemas.advice import (
    KnowledgeAccessContext,
    KnowledgeBusinessContext,
)
from app.services.bm25_knowledge_store import LocalBm25KnowledgeStore, tokenize_text
from app.services.knowledge_retrievers import Bm25KnowledgeRetriever, TfidfKnowledgeRetriever, create_default_knowledge_retriever


def test_tokenize_text_supports_chinese_ngrams_and_english_terms():
    tokens = tokenize_text("深圳 管制空域 inspection")

    assert "深" in tokens
    assert "深圳" in tokens
    assert "管制" in tokens
    assert "制空" in tokens
    assert "管制空" in tokens
    assert "inspection" in tokens


def test_bm25_retrieves_keyword_match_and_preserves_metadata_filters(tmp_path):
    knowledge_path = tmp_path / "advice_rules.json"
    index_dir = tmp_path / "index"
    knowledge_path.write_text(json.dumps(_knowledge_payload(), ensure_ascii=False), encoding="utf-8")
    store = LocalBm25KnowledgeStore(knowledge_path=knowledge_path, index_dir=index_dir)

    result = store.retrieve(
        "深圳 管制空域 实名登记",
        top_k=3,
        access_context=KnowledgeAccessContext(user_id="user-a", tenant_id="public", role="user"),
        business_context=KnowledgeBusinessContext(task_type="inspection", risk_tags=[], city="深圳", province="广东"),
    )

    assert [item.id for item in result] == ["policy-shenzhen"]
    assert result[0].score > 0
    assert result[0].metadata["retriever"] == "bm25"
    assert (index_dir / "bm25_index.pkl").exists()
    assert (index_dir / "bm25_documents.json").exists()


def test_bm25_respects_private_user_visibility(tmp_path):
    knowledge_path = tmp_path / "advice_rules.json"
    index_dir = tmp_path / "index"
    payload = _knowledge_payload()
    payload["items"].append(
        {
            **payload["items"][0],
            "id": "private-user-b",
            "title": "用户 B 私有禁飞区",
            "advice_text": "用户 B 私有禁飞区巡检说明。",
            "visibility": "private",
            "user_id": "user-b",
            "keywords": ["私有禁飞区"],
        }
    )
    knowledge_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    store = LocalBm25KnowledgeStore(knowledge_path=knowledge_path, index_dir=index_dir)

    result = store.retrieve(
        "私有禁飞区",
        top_k=5,
        access_context=KnowledgeAccessContext(user_id="user-a", tenant_id="public", role="user"),
        business_context=KnowledgeBusinessContext(task_type="inspection", risk_tags=[], city="深圳", province="广东"),
    )

    assert "private-user-b" not in [item.id for item in result]


def test_default_retriever_can_switch_between_bm25_and_tfidf(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_RETRIEVER", "bm25")
    assert isinstance(create_default_knowledge_retriever(), Bm25KnowledgeRetriever)

    monkeypatch.setenv("KNOWLEDGE_RETRIEVER", "tfidf")
    assert isinstance(create_default_knowledge_retriever(), TfidfKnowledgeRetriever)

    monkeypatch.setenv("KNOWLEDGE_RETRIEVER", "unknown")
    assert isinstance(create_default_knowledge_retriever(), TfidfKnowledgeRetriever)


def _knowledge_payload():
    return {
        "version": "v1",
        "items": [
            {
                "id": "policy-shenzhen",
                "category": "risk_advice",
                "knowledge_type": "policy_hint",
                "risk_type": [],
                "task_type": ["inspection"],
                "warning_type": [],
                "warning_level": [],
                "decision_scope": [],
                "region": "深圳",
                "province": "广东",
                "city": "深圳",
                "visibility": "public",
                "tenant_id": "public",
                "user_id": None,
                "version": "v1",
                "effective_at": None,
                "expires_at": None,
                "review_status": "approved",
                "title": "深圳管制空域与实名登记提示",
                "advice_text": "深圳无人机巡检需要关注管制空域和实名登记要求。",
                "priority": "high",
                "action_type": "reduce_risk",
                "keywords": ["深圳", "管制空域", "实名登记"],
                "source": "local sample",
                "source_url": None,
                "notes": None,
            },
            {
                "id": "policy-guangzhou",
                "category": "risk_advice",
                "knowledge_type": "policy_hint",
                "risk_type": [],
                "task_type": ["inspection"],
                "warning_type": [],
                "warning_level": [],
                "decision_scope": [],
                "region": "广州",
                "province": "广东",
                "city": "广州",
                "visibility": "public",
                "tenant_id": "public",
                "user_id": None,
                "version": "v1",
                "effective_at": None,
                "expires_at": None,
                "review_status": "approved",
                "title": "广州巡检提示",
                "advice_text": "广州巡检需要关注城市低空作业要求。",
                "priority": "medium",
                "action_type": "reduce_risk",
                "keywords": ["广州", "巡检"],
                "source": "local sample",
                "source_url": None,
                "notes": None,
            },
        ],
    }
