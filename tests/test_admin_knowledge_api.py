from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import KnowledgeDocument, KnowledgeIndexJob, User
from app.dependencies import get_db
from app.services.auth_service import create_access_token, hash_password
from main import app


def build_test_client() -> tuple[TestClient, sessionmaker[Session]]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        db.add_all(
            [
                User(
                    id="admin-a",
                    username="admin_a",
                    password_hash=hash_password("admin123456"),
                    role="admin",
                    is_active=True,
                ),
                User(
                    id="user-a",
                    username="user_a",
                    password_hash=hash_password("user123456"),
                    role="user",
                    is_active=True,
                ),
            ]
        )
        db.commit()

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), TestingSessionLocal


def auth_headers(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def valid_knowledge_payload(title: str = "深圳大风巡检处置") -> dict:
    return {
        "title": title,
        "content": "深圳大风条件下应降低巡检任务复杂度或改期。",
        "knowledge_type": "risk_advice",
        "category": "risk_advice",
        "province": "广东",
        "city": "深圳",
        "task_types": ["inspection"],
        "risk_tags": ["high_wind"],
        "warning_types": ["大风"],
        "warning_levels": ["yellow"],
        "decision_scopes": ["慎飞"],
        "keywords": ["大风", "巡检", "改期"],
        "visibility": "public",
        "tenant_id": "public",
        "version": "v1",
        "review_status": "draft",
        "is_active": True,
        "source": "manual",
        "metadata": {"editor": "admin-a"},
    }


def test_admin_knowledge_requires_admin_role() -> None:
    client, _ = build_test_client()
    try:
        response = client.get("/admin/knowledge", headers=auth_headers("user-a"))

        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_admin_can_create_list_get_update_status_and_soft_delete_knowledge() -> None:
    client, SessionLocal = build_test_client()
    try:
        create_response = client.post(
            "/admin/knowledge",
            json=valid_knowledge_payload(),
            headers=auth_headers("admin-a"),
        )
        assert create_response.status_code == 201
        created = create_response.json()
        knowledge_id = created["id"]
        assert created["index_dirty"] is True
        assert created["review_status"] == "draft"
        assert created["risk_tags"] == ["high_wind"]

        list_response = client.get(
            "/admin/knowledge?knowledge_type=risk_advice&city=深圳&index_dirty=true",
            headers=auth_headers("admin-a"),
        )
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1

        get_response = client.get(f"/admin/knowledge/{knowledge_id}", headers=auth_headers("admin-a"))
        assert get_response.status_code == 200
        assert get_response.json()["title"] == "深圳大风巡检处置"

        patch_response = client.patch(
            f"/admin/knowledge/{knowledge_id}",
            json={"title": "深圳大风巡检更新", "risk_tags": ["high_wind", "operation_change"]},
            headers=auth_headers("admin-a"),
        )
        assert patch_response.status_code == 200
        assert patch_response.json()["title"] == "深圳大风巡检更新"
        assert patch_response.json()["risk_tags"] == ["high_wind", "operation_change"]
        assert patch_response.json()["index_dirty"] is True

        status_response = client.post(
            f"/admin/knowledge/{knowledge_id}/status",
            json={"review_status": "approved", "is_active": True},
            headers=auth_headers("admin-a"),
        )
        assert status_response.status_code == 200
        assert status_response.json()["review_status"] == "approved"
        assert status_response.json()["is_active"] is True
        assert status_response.json()["index_dirty"] is True

        delete_response = client.delete(f"/admin/knowledge/{knowledge_id}", headers=auth_headers("admin-a"))
        assert delete_response.status_code == 200
        assert delete_response.json()["is_active"] is False
        assert delete_response.json()["index_dirty"] is True

        with SessionLocal() as db:
            persisted = db.get(KnowledgeDocument, knowledge_id)
            assert persisted is not None
            assert persisted.is_active is False
            assert persisted.index_dirty is True
    finally:
        app.dependency_overrides.clear()


def test_admin_can_reindex_approved_active_knowledge(monkeypatch, tmp_path) -> None:
    import app.services.admin_knowledge_indexing as indexing
    import app.services.vector_knowledge_store as vector_store

    generated_source_path = tmp_path / "knowledge_documents_source.json"
    monkeypatch.setattr(indexing, "DEFAULT_DB_KNOWLEDGE_PATH", generated_source_path)
    monkeypatch.setattr(vector_store, "DEFAULT_DB_KNOWLEDGE_PATH", generated_source_path)

    client, SessionLocal = build_test_client()
    try:
        create_response = client.post(
            "/admin/knowledge",
            json={
                **valid_knowledge_payload(),
                "review_status": "approved",
                "is_active": True,
            },
            headers=auth_headers("admin-a"),
        )
        assert create_response.status_code == 201
        knowledge_id = create_response.json()["id"]
        excluded_payloads = [
            {**valid_knowledge_payload("未审核知识"), "review_status": "draft", "is_active": True},
            {**valid_knowledge_payload("禁用知识"), "review_status": "approved", "is_active": False},
            {
                **valid_knowledge_payload("过期知识"),
                "review_status": "approved",
                "is_active": True,
                "expires_at": "2020-01-01T00:00:00",
            },
        ]
        for payload in excluded_payloads:
            response = client.post("/admin/knowledge", json=payload, headers=auth_headers("admin-a"))
            assert response.status_code == 201

        reindex_response = client.post("/admin/knowledge/reindex", headers=auth_headers("admin-a"))
        assert reindex_response.status_code == 200
        job_payload = reindex_response.json()
        assert job_payload["status"] == "success"
        assert job_payload["document_count"] == 1
        assert job_payload["chunk_count"] >= 1
        assert job_payload["triggered_by_user_id"] == "admin-a"

        jobs_response = client.get("/admin/knowledge/index-jobs", headers=auth_headers("admin-a"))
        assert jobs_response.status_code == 200
        assert jobs_response.json()["total"] == 1

        with SessionLocal() as db:
            document = db.get(KnowledgeDocument, knowledge_id)
            assert document is not None
            assert document.index_dirty is False
            excluded_documents = [
                item for item in db.query(KnowledgeDocument).all() if item.id != knowledge_id
            ]
            assert excluded_documents
            assert all(item.index_dirty is True for item in excluded_documents)
            job = db.get(KnowledgeIndexJob, job_payload["id"])
            assert job is not None
            assert job.status == "success"
    finally:
        app.dependency_overrides.clear()


def test_admin_knowledge_returns_404_for_missing_document() -> None:
    client, _ = build_test_client()
    try:
        response = client.get("/admin/knowledge/missing", headers=auth_headers("admin-a"))

        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
