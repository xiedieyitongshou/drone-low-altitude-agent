import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import scripts.import_knowledge_json as importer
from app.db.base import Base
from app.db.models import KnowledgeDocument


def build_session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def test_import_knowledge_json_upserts_documents(monkeypatch, tmp_path) -> None:
    SessionLocal = build_session_factory()
    monkeypatch.setattr(importer, "SessionLocal", SessionLocal)
    monkeypatch.setattr(importer, "engine", SessionLocal.kw["bind"])
    knowledge_path = tmp_path / "advice_rules.json"
    knowledge_path.write_text(json.dumps(_knowledge_payload("原始标题"), ensure_ascii=False), encoding="utf-8")

    first_result = importer.import_knowledge_json(knowledge_path)
    knowledge_path.write_text(json.dumps(_knowledge_payload("更新标题"), ensure_ascii=False), encoding="utf-8")
    second_result = importer.import_knowledge_json(knowledge_path)

    with SessionLocal() as db:
        documents = list(db.scalars(select(KnowledgeDocument)))
        document = documents[0]

    assert first_result.created == 1
    assert first_result.updated == 0
    assert second_result.created == 0
    assert second_result.updated == 1
    assert len(documents) == 1
    assert document.id == "knowledge-1"
    assert document.title == "更新标题"
    assert document.content == "遇到高风时应改期。"
    assert document.knowledge_type == "risk_advice"
    assert document.category == "risk_advice"
    assert document.risk_tags_json == ["high_wind"]
    assert document.task_types_json == ["inspection"]
    assert document.visibility == "public"
    assert document.review_status == "approved"
    assert document.is_active is True
    assert document.index_dirty is True
    assert document.metadata_json["priority"] == "high"
    assert document.metadata_json["action_type"] == "reschedule"
    assert document.metadata_json["source_format"] == "json_import"


def _knowledge_payload(title: str) -> dict:
    return {
        "version": "v1",
        "items": [
            {
                "id": "knowledge-1",
                "category": "risk_advice",
                "risk_type": ["high_wind"],
                "task_type": ["inspection"],
                "warning_type": ["大风"],
                "warning_level": ["yellow"],
                "decision_scope": ["caution"],
                "title": title,
                "advice_text": "遇到高风时应改期。",
                "priority": "high",
                "action_type": "reschedule",
                "keywords": ["高风", "改期"],
                "source": "test source",
                "source_url": None,
                "notes": "测试备注",
                "knowledge_type": "risk_advice",
                "region": None,
                "province": "广东",
                "city": "深圳",
                "visibility": "public",
                "tenant_id": "public",
                "user_id": None,
                "version": "v1",
                "effective_at": None,
                "expires_at": None,
                "review_status": "approved",
            }
        ],
    }
