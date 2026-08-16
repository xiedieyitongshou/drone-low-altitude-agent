from collections.abc import Generator
from unittest.mock import ANY, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import User
from app.dependencies import get_db
from app.schemas import OrchestratorResponse
from app.services.auth_service import create_access_token, hash_password
from main import app


def build_test_client() -> tuple[TestClient, str]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        user = User(
            id="real-user-id",
            username="demo",
            password_hash=hash_password("demo123456"),
            display_name="Demo User",
            role="user",
            is_active=True,
        )
        db.add(user)
        db.commit()

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), create_access_token("real-user-id")


def test_agent_query_requires_login() -> None:
    client, _ = build_test_client()
    try:
        response = client.post("/agent/query", json={"query": "深圳明天下午可以飞吗"})

        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_agent_query_uses_token_user_not_payload_user_id() -> None:
    client, token = build_test_client()
    orchestrator_response = OrchestratorResponse(
        session_id="session-1",
        user_id="real-user-id",
        conversation_id="conversation-1",
        intent="evaluate",
        target_endpoint="/cruise/evaluate",
        parser_source="rule",
        parsed={"location": "深圳"},
        message="ok",
    )

    try:
        with patch("main.orchestrate_task_query", return_value=orchestrator_response) as orchestrate_mock:
            response = client.post(
                "/agent/query",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "session_id": "session-1",
                    "user_id": "spoofed-user-id",
                    "query": "深圳明天下午可以飞吗",
                },
            )

        assert response.status_code == 200
        assert response.json()["user_id"] == "real-user-id"
        orchestrate_mock.assert_called_once_with(
            "深圳明天下午可以飞吗",
            session_id="session-1",
            user_id="real-user-id",
            db=ANY,
        )
    finally:
        app.dependency_overrides.clear()
