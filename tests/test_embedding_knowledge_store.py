import json

from app.schemas.advice import KnowledgeAccessContext, KnowledgeBusinessContext
from app.services.embedding_knowledge_store import LocalEmbeddingKnowledgeStore
from app.services.embedding_providers import MockEmbeddingProvider


def test_mock_embedding_provider_is_deterministic_and_normalized():
    provider = MockEmbeddingProvider(dimension=64)

    first = provider.embed_texts(["深圳低空飞行手续"])[0]
    second = provider.embed_texts(["深圳低空飞行手续"])[0]

    assert first == second
    assert len(first) == 64
    assert round(sum(value * value for value in first), 6) == 1


def test_embedding_retrieves_semantic_match_and_records_metadata(tmp_path):
    knowledge_path = tmp_path / "advice_rules.json"
    index_dir = tmp_path / "index"
    knowledge_path.write_text(json.dumps(_knowledge_payload(), ensure_ascii=False), encoding="utf-8")
    store = LocalEmbeddingKnowledgeStore(
        provider=MockEmbeddingProvider(dimension=128),
        knowledge_path=knowledge_path,
        index_dir=index_dir,
        min_score=0.1,
    )

    result = store.retrieve(
        "这个地方飞之前要不要办手续",
        top_k=3,
        access_context=KnowledgeAccessContext(user_id="user-a", tenant_id="public", role="user"),
        business_context=KnowledgeBusinessContext(task_type="inspection", risk_tags=[], city="深圳", province="广东"),
    )

    assert [item.id for item in result] == ["policy-shenzhen"]
    assert result[0].metadata["retriever"] == "embedding"
    assert result[0].metadata["embedding_provider"] == "mock"
    assert result[0].metadata["embedding_model"] == "hash-ngram-v1"
    assert result[0].metadata["embedding_dimension"] == 128
    assert result[0].metadata["min_score"] == 0.1
    assert result[0].metadata["knowledge_id"] == "policy-shenzhen"
    assert result[0].metadata["chunk_id"].startswith("policy-shenzhen::chunk-")
    assert result[0].metadata["chunk_type"] == "policy_clause"
    assert result[0].metadata["rerank_boost"] > 0


def test_embedding_respects_private_user_visibility(tmp_path):
    knowledge_path = tmp_path / "advice_rules.json"
    index_dir = tmp_path / "index"
    payload = _knowledge_payload()
    payload["items"].append(
        {
            **payload["items"][0],
            "id": "private-user-b",
            "title": "用户 B 私有审批规则",
            "advice_text": "用户 B 私有飞行审批说明。",
            "visibility": "private",
            "user_id": "user-b",
            "keywords": ["私有审批"],
        }
    )
    knowledge_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    store = LocalEmbeddingKnowledgeStore(
        provider=MockEmbeddingProvider(dimension=128),
        knowledge_path=knowledge_path,
        index_dir=index_dir,
        min_score=0.0,
    )

    result = store.retrieve(
        "私有审批",
        top_k=5,
        access_context=KnowledgeAccessContext(user_id="user-a", tenant_id="public", role="user"),
        business_context=KnowledgeBusinessContext(task_type="inspection", risk_tags=[], city="深圳", province="广东"),
    )

    assert "private-user-b" not in [item.id for item in result]


def test_embedding_index_rebuilds_when_provider_metadata_changes(tmp_path):
    knowledge_path = tmp_path / "advice_rules.json"
    index_dir = tmp_path / "index"
    knowledge_path.write_text(json.dumps(_knowledge_payload(), ensure_ascii=False), encoding="utf-8")

    first_store = LocalEmbeddingKnowledgeStore(
        provider=MockEmbeddingProvider(dimension=64),
        knowledge_path=knowledge_path,
        index_dir=index_dir,
    )
    first_store.build_index()
    first_metadata = json.loads((index_dir / "embedding_metadata.json").read_text(encoding="utf-8"))
    assert first_metadata["dimension"] == 64

    second_store = LocalEmbeddingKnowledgeStore(
        provider=MockEmbeddingProvider(dimension=128),
        knowledge_path=knowledge_path,
        index_dir=index_dir,
    )
    second_store.retrieve("审批手续", top_k=1)

    second_metadata = json.loads((index_dir / "embedding_metadata.json").read_text(encoding="utf-8"))
    assert second_metadata["dimension"] == 128


def test_embedding_min_score_filters_low_confidence_results(tmp_path):
    knowledge_path = tmp_path / "advice_rules.json"
    index_dir = tmp_path / "index"
    knowledge_path.write_text(json.dumps(_knowledge_payload(), ensure_ascii=False), encoding="utf-8")
    store = LocalEmbeddingKnowledgeStore(
        provider=MockEmbeddingProvider(dimension=128),
        knowledge_path=knowledge_path,
        index_dir=index_dir,
        min_score=0.95,
    )

    result = store.retrieve(
        "完全无关的电池保养话题",
        top_k=3,
        access_context=KnowledgeAccessContext(user_id="user-a", tenant_id="public", role="user"),
        business_context=KnowledgeBusinessContext(task_type="inspection", risk_tags=[], city="深圳", province="广东"),
    )

    assert result == []


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
                "title": "深圳无人机飞行审批与报备提示",
                "advice_text": "深圳无人机巡检需要关注审批、报备、许可和管制空域要求。",
                "priority": "high",
                "action_type": "reduce_risk",
                "keywords": ["深圳", "手续", "审批", "报备", "许可", "管制空域"],
                "source": "local sample",
                "source_url": None,
                "notes": None,
            },
            {
                "id": "weather-guangzhou",
                "category": "risk_advice",
                "knowledge_type": "risk_advice",
                "risk_type": ["rain"],
                "task_type": ["inspection"],
                "warning_type": ["rain"],
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
                "title": "广州降雨巡检提示",
                "advice_text": "广州巡检需要关注降雨、能见度和地面积水。",
                "priority": "medium",
                "action_type": "reduce_risk",
                "keywords": ["广州", "降雨", "能见度"],
                "source": "local sample",
                "source_url": None,
                "notes": None,
            },
        ],
    }
