from collections.abc import Generator
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import ConversationRecord, User
from app.dependencies import get_db
from app.services.auth_service import create_access_token, hash_password
from main import app


def build_test_client() -> tuple[TestClient, dict[str, str]]:
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
                User(
                    id="user-b",
                    username="user_b",
                    password_hash=hash_password("user123456"),
                    role="user",
                    is_active=False,
                ),
            ]
        )
        db.flush()
        db.add_all(
            [
                ConversationRecord(
                    conversation_id="conv-ok",
                    user_id="user-a",
                    query="深圳适飞吗",
                    success=True,
                    message="适飞",
                    response_json={"overall_decision": "适飞", "allow_execute": True},
                    created_at=datetime.utcnow(),
                ),
                ConversationRecord(
                    conversation_id="conv-risk",
                    user_id="user-a",
                    query="台风天能飞吗",
                    success=True,
                    message="禁飞",
                    response_json={"overall_decision": "禁飞", "allow_execute": False},
                    created_at=datetime.utcnow(),
                ),
                ConversationRecord(
                    conversation_id="conv-parse-failed",
                    user_id="user-b",
                    query="随便看看",
                    parser_source="parser",
                    success=False,
                    message="解析失败",
                    response_json={"error": "parse failed"},
                    created_at=datetime.utcnow(),
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
    return TestClient(app), {
        "admin-a": create_access_token("admin-a"),
        "user-a": create_access_token("user-a"),
    }


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_admin_stats_requires_admin_role() -> None:
    client, tokens = build_test_client()
    try:
        response = client.get("/admin/stats/tasks", headers=auth_headers(tokens["user-a"]))

        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_admin_stats_returns_task_and_user_metrics() -> None:
    client, tokens = build_test_client()
    try:
        response = client.get("/admin/stats/tasks", headers=auth_headers(tokens["admin-a"]))

        assert response.status_code == 200
        payload = response.json()
        assert payload["total_users"] == 3
        assert payload["active_users"] == 2
        assert payload["disabled_users"] == 1
        assert payload["admin_users"] == 1
        assert payload["total_tasks"] == 3
        assert payload["successful_tasks"] == 2
        assert payload["failed_tasks"] == 1
        assert payload["high_risk_tasks"] == 1
        assert payload["rule_rejected_tasks"] == 1
        assert payload["parser_failed_tasks"] == 1
    finally:
        app.dependency_overrides.clear()
