from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import KnowledgeDocument, KnowledgeIndexJob, User
from app.schemas import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentResponse,
    KnowledgeIndexJobResponse,
    KnowledgeIndexJobStatus,
)
from app.schemas.advice import KnowledgeReviewStatus, KnowledgeType, KnowledgeVisibility


def build_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return TestingSessionLocal()


def test_knowledge_document_persists_governance_fields() -> None:
    with build_session() as db:
        db.add(
            User(
                id="admin-a",
                username="admin_a",
                password_hash="hashed",
                role="admin",
                is_active=True,
            )
        )
        db.add(
            KnowledgeDocument(
                id="knowledge-1",
                title="深圳低空巡航雷雨处置",
                content="雷雨预警下应延后或取消低空巡航任务。",
                knowledge_type="risk_advice",
                category="warning_advice",
                province="广东",
                city="深圳",
                task_types_json=["cruise"],
                risk_tags_json=["weather_warning"],
                warning_types_json=["雷电"],
                warning_levels_json=["orange", "red"],
                decision_scopes_json=["禁飞"],
                visibility="tenant",
                tenant_id="tenant-a",
                user_id="admin-a",
                version="v1",
                review_status="approved",
                is_active=True,
                index_dirty=True,
                metadata_json={"source_format": "json_import"},
            )
        )
        db.commit()

        persisted = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id == "knowledge-1"))

        assert persisted is not None
        assert persisted.review_status == "approved"
        assert persisted.is_active is True
        assert persisted.index_dirty is True
        assert persisted.visibility == "tenant"
        assert persisted.tenant_id == "tenant-a"
        assert persisted.user_id == "admin-a"
        assert persisted.risk_tags_json == ["weather_warning"]
        assert persisted.metadata_json["source_format"] == "json_import"


def test_knowledge_index_job_persists_rebuild_status() -> None:
    with build_session() as db:
        db.add(
            KnowledgeIndexJob(
                id="job-1",
                status="success",
                index_type="hybrid",
                document_count=12,
                chunk_count=48,
            )
        )
        db.commit()

        persisted = db.scalar(select(KnowledgeIndexJob).where(KnowledgeIndexJob.id == "job-1"))

        assert persisted is not None
        assert persisted.status == "success"
        assert persisted.index_type == "hybrid"
        assert persisted.document_count == 12
        assert persisted.chunk_count == 48


def test_knowledge_management_schema_reuses_rag_metadata_fields() -> None:
    payload = KnowledgeDocumentCreate(
        title="高风风险处置",
        content="风速偏高时应降低任务复杂度或改期。",
        knowledge_type=KnowledgeType.RISK_ADVICE,
        risk_tags=["high_wind"],
        task_types=["inspection"],
        visibility=KnowledgeVisibility.PUBLIC,
        review_status=KnowledgeReviewStatus.APPROVED,
    )
    response = KnowledgeDocumentResponse(
        id="knowledge-2",
        created_at="2026-08-15T10:00:00",
        updated_at="2026-08-15T10:00:00",
        **payload.model_dump(),
    )
    job = KnowledgeIndexJobResponse(
        id="job-2",
        status=KnowledgeIndexJobStatus.PENDING,
        created_at="2026-08-15T10:00:00",
        updated_at="2026-08-15T10:00:00",
    )

    assert response.knowledge_type == KnowledgeType.RISK_ADVICE
    assert response.risk_tags == ["high_wind"]
    assert response.index_dirty is True
    assert job.status == KnowledgeIndexJobStatus.PENDING
