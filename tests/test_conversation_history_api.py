from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import ConversationRecord, User
from app.services.auth_service import create_access_token, hash_password


@pytest.fixture
def conversation_tokens(api_session_factory: sessionmaker[Session]) -> dict[str, str]:
    now = datetime.utcnow()
    with api_session_factory() as db:
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

    return {"user-a": create_access_token("user-a"), "user-b": create_access_token("user-b")}


@pytest.mark.usefixtures("conversation_tokens")
def test_conversation_list_requires_login(api_client: TestClient) -> None:
    response = api_client.get("/agent/conversations")

    assert response.status_code == 401


def test_conversation_list_is_scoped_to_current_user(api_client: TestClient, conversation_tokens: dict[str, str]) -> None:
    response = api_client.get(
        "/agent/conversations",
        headers={"Authorization": f"Bearer {conversation_tokens['user-a']}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert [item["conversation_id"] for item in payload["items"]] == ["conv-a-2", "conv-a-1"]


def test_keyword_search_does_not_cross_user_boundary(api_client: TestClient, conversation_tokens: dict[str, str]) -> None:
    response = api_client.get(
        "/agent/conversations?keyword=深圳",
        headers={"Authorization": f"Bearer {conversation_tokens['user-a']}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["conversation_id"] == "conv-a-1"


def test_conversation_detail_requires_owner(api_client: TestClient, conversation_tokens: dict[str, str]) -> None:
    own_response = api_client.get(
        "/agent/conversations/conv-a-1",
        headers={"Authorization": f"Bearer {conversation_tokens['user-a']}"},
    )
    assert own_response.status_code == 200
    assert own_response.json()["parsed"] == {"location": "深圳"}

    other_response = api_client.get(
        "/agent/conversations/conv-b-1",
        headers={"Authorization": f"Bearer {conversation_tokens['user-a']}"},
    )
    assert other_response.status_code == 404


def test_conversation_list_supports_filters_and_pagination(api_client: TestClient, conversation_tokens: dict[str, str]) -> None:
    response = api_client.get(
        "/agent/conversations?page=1&page_size=1&intent=recommend&parser_source=llm",
        headers={"Authorization": f"Bearer {conversation_tokens['user-a']}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["page"] == 1
    assert payload["page_size"] == 1
    assert payload["items"][0]["conversation_id"] == "conv-a-2"
