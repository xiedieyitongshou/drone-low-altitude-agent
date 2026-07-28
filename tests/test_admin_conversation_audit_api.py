from collections.abc import Generator
from datetime import datetime, timedelta

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

    now = datetime(2026, 7, 28, 10, 0, 0)
    with TestingSessionLocal() as db:
        db.add_all(
            [
                User(
                    id="admin-a",
                    username="admin_a",
                    password_hash=hash_password("admin123456"),
                    display_name="Admin A",
                    role="admin",
                    is_active=True,
                ),
                User(
                    id="user-a",
                    username="user_a",
                    password_hash=hash_password("user123456"),
                    display_name="User A",
                    role="user",
                    is_active=True,
                ),
                User(
                    id="user-b",
                    username="user_b",
                    password_hash=hash_password("user123456"),
                    display_name="User B",
                    role="user",
                    is_active=True,
                ),
            ]
        )
        db.flush()
        db.add_all(
            [
                ConversationRecord(
                    conversation_id="conv-a-1",
                    session_id="session-a",
                    user_id="user-a",
                    query="深圳明天下午可以飞吗",
                    intent="evaluate",
                    target_endpoint="/cruise/evaluate",
                    parser_source="rule",
                    parsed_json={"location": "深圳"},
                    context_used=False,
                    success=True,
                    message="已完成深圳评估",
                    explanation="深圳明天下午整体适飞。",
                    response_json={"overall_decision": "适飞"},
                    created_at=now,
                ),
                ConversationRecord(
                    conversation_id="conv-a-2",
                    session_id="session-a",
                    user_id="user-a",
                    query="广州未来72小时最佳窗口",
                    intent="recommend",
                    target_endpoint="/cruise/recommend",
                    parser_source="llm",
                    parsed_json={"location": "广州"},
                    context_used=True,
                    success=False,
                    message="LLM 解析失败",
                    explanation="缺少有效天气数据。",
                    response_json={"error": "weather unavailable"},
                    created_at=now + timedelta(hours=1),
                ),
                ConversationRecord(
                    conversation_id="conv-b-1",
                    session_id="session-b",
                    user_id="user-b",
                    query="珠海低空巡检风险排查",
                    intent="evaluate",
                    target_endpoint="/cruise/evaluate",
                    parser_source="rule",
                    parsed_json={"location": "珠海"},
                    context_used=False,
                    success=True,
                    message="用户 B 的珠海记录",
                    explanation="珠海存在阵风风险。",
                    response_json={"overall_decision": "谨慎飞行"},
                    created_at=now + timedelta(hours=2),
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
        "user-b": create_access_token("user-b"),
    }


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_admin_conversations_requires_admin_role() -> None:
    client, tokens = build_test_client()
    try:
        response = client.get("/admin/conversations", headers=auth_headers(tokens["user-a"]))

        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_admin_can_list_conversations_across_users() -> None:
    client, tokens = build_test_client()
    try:
        response = client.get("/admin/conversations", headers=auth_headers(tokens["admin-a"]))

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 3
        assert [item["conversation_id"] for item in payload["items"]] == [
            "conv-b-1",
            "conv-a-2",
            "conv-a-1",
        ]
        assert payload["items"][0]["user_id"] == "user-b"
        assert payload["items"][0]["username"] == "user_b"
    finally:
        app.dependency_overrides.clear()


def test_admin_conversations_support_filters() -> None:
    client, tokens = build_test_client()
    try:
        response = client.get(
            "/admin/conversations?user_id=user-a&success=false&parser_source=llm",
            headers=auth_headers(tokens["admin-a"]),
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["conversation_id"] == "conv-a-2"

        time_response = client.get(
            "/admin/conversations?created_from=2026-07-28T11:30:00&created_to=2026-07-28T12:30:00",
            headers=auth_headers(tokens["admin-a"]),
        )

        assert time_response.status_code == 200
        assert time_response.json()["total"] == 1
        assert time_response.json()["items"][0]["conversation_id"] == "conv-b-1"
    finally:
        app.dependency_overrides.clear()


def test_admin_can_get_any_conversation_detail_readonly() -> None:
    client, tokens = build_test_client()
    try:
        response = client.get(
            "/admin/conversations/conv-b-1",
            headers=auth_headers(tokens["admin-a"]),
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["user_id"] == "user-b"
        assert payload["parsed"] == {"location": "珠海"}
        assert payload["response"] == {"overall_decision": "谨慎飞行"}

        patch_response = client.patch(
            "/admin/conversations/conv-b-1",
            json={"message": "changed"},
            headers=auth_headers(tokens["admin-a"]),
        )
        assert patch_response.status_code == 405
    finally:
        app.dependency_overrides.clear()


def test_admin_conversation_detail_returns_404_for_missing_record() -> None:
    client, tokens = build_test_client()
    try:
        response = client.get(
            "/admin/conversations/missing",
            headers=auth_headers(tokens["admin-a"]),
        )

        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
