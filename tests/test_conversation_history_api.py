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

    now = datetime.utcnow()
    with TestingSessionLocal() as db:
        db.add_all(
            [
                User(
                    id="user-a",
                    username="user_a",
                    password_hash=hash_password("demo123456"),
                    display_name="User A",
                    role="user",
                    is_active=True,
                ),
                User(
                    id="user-b",
                    username="user_b",
                    password_hash=hash_password("demo123456"),
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
                    response_json={"user_id": "user-a"},
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
                    success=True,
                    message="已完成广州推荐",
                    explanation="广州存在推荐窗口。",
                    response_json={"user_id": "user-a"},
                    created_at=now + timedelta(minutes=1),
                ),
                ConversationRecord(
                    conversation_id="conv-b-1",
                    session_id="session-b",
                    user_id="user-b",
                    query="深圳禁飞风险排查",
                    intent="evaluate",
                    target_endpoint="/cruise/evaluate",
                    parser_source="rule",
                    parsed_json={"location": "深圳"},
                    context_used=False,
                    success=True,
                    message="用户 B 的深圳记录",
                    explanation="用户 B 私有记录。",
                    response_json={"user_id": "user-b"},
                    created_at=now + timedelta(minutes=2),
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
        "user-a": create_access_token("user-a"),
        "user-b": create_access_token("user-b"),
    }


def test_conversation_list_requires_login() -> None:
    client, _ = build_test_client()
    try:
        response = client.get("/agent/conversations")

        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_conversation_list_is_scoped_to_current_user() -> None:
    client, tokens = build_test_client()
    try:
        response = client.get(
            "/agent/conversations",
            headers={"Authorization": f"Bearer {tokens['user-a']}"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 2
        assert [item["conversation_id"] for item in payload["items"]] == ["conv-a-2", "conv-a-1"]
    finally:
        app.dependency_overrides.clear()


def test_keyword_search_does_not_cross_user_boundary() -> None:
    client, tokens = build_test_client()
    try:
        response = client.get(
            "/agent/conversations?keyword=深圳",
            headers={"Authorization": f"Bearer {tokens['user-a']}"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["items"][0]["conversation_id"] == "conv-a-1"
    finally:
        app.dependency_overrides.clear()


def test_conversation_detail_requires_owner() -> None:
    client, tokens = build_test_client()
    try:
        own_response = client.get(
            "/agent/conversations/conv-a-1",
            headers={"Authorization": f"Bearer {tokens['user-a']}"},
        )
        assert own_response.status_code == 200
        assert own_response.json()["parsed"] == {"location": "深圳"}

        other_response = client.get(
            "/agent/conversations/conv-b-1",
            headers={"Authorization": f"Bearer {tokens['user-a']}"},
        )
        assert other_response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_conversation_list_supports_filters_and_pagination() -> None:
    client, tokens = build_test_client()
    try:
        response = client.get(
            "/agent/conversations?page=1&page_size=1&intent=recommend&parser_source=llm",
            headers={"Authorization": f"Bearer {tokens['user-a']}"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["page"] == 1
        assert payload["page_size"] == 1
        assert payload["items"][0]["conversation_id"] == "conv-a-2"
    finally:
        app.dependency_overrides.clear()
