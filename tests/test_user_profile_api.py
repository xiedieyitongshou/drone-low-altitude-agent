import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import User, UserProfile
from app.services.auth_service import create_access_token, hash_password
from app.services.nl_parser import parse_natural_language_request
from app.services.profile_memory import get_or_create_user_profile, merge_profile_context, update_profile_from_parsed


@pytest.fixture
def profile_tokens(api_session_factory: sessionmaker[Session]) -> dict[str, str]:
    with api_session_factory() as db:
        db.add_all(
            [
                User(
                    id="user-a",
                    username="user_a",
                    password_hash=hash_password("demo123456"),
                    role="user",
                    is_active=True,
                ),
                User(
                    id="user-b",
                    username="user_b",
                    password_hash=hash_password("demo123456"),
                    role="user",
                    is_active=True,
                ),
            ]
        )
        db.commit()

    return {"user-a": create_access_token("user-a"), "user-b": create_access_token("user-b")}


def test_get_profile_creates_current_user_profile(api_client: TestClient, profile_tokens: dict[str, str]) -> None:
    response = api_client.get(
        "/users/me/profile",
        headers={"Authorization": f"Bearer {profile_tokens['user-a']}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["user_id"] == "user-a"
    assert payload["default_task_type"] == "cruise"
    assert payload["common_task_types"] == ["cruise"]


def test_patch_profile_updates_only_current_user(
    api_client: TestClient, profile_tokens: dict[str, str], api_session_factory: sessionmaker[Session]
) -> None:
    headers = {"Authorization": f"Bearer {profile_tokens['user-a']}"}
    response = api_client.patch(
        "/users/me/profile",
        headers=headers,
        json={
            "default_location": "深圳湾",
            "default_task_type": "inspection",
            "default_start_time": "14:00",
            "default_end_time": "17:00",
            "output_style": "detailed",
            "common_locations": ["深圳湾", "南山区", "深圳湾"],
            "common_task_types": ["inspection", "survey", "inspection"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["user_id"] == "user-a"
    assert payload["default_location"] == "深圳湾"
    assert payload["default_task_type"] == "inspection"
    assert payload["common_locations"] == ["深圳湾", "南山区"]
    assert payload["common_task_types"] == ["inspection", "survey"]

    stored_profile = api_client.get("/users/me/profile", headers=headers)
    assert stored_profile.status_code == 200
    assert stored_profile.json() == payload

    with api_session_factory() as db:
        user_b_profile = db.scalar(select(UserProfile).where(UserProfile.user_id == "user-b"))
        assert user_b_profile is None


def test_profile_context_fills_missing_task_fields(
    api_client: TestClient,
    profile_tokens: dict[str, str],
    api_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert api_client.patch(
        "/users/me/profile",
        headers={"Authorization": f"Bearer {profile_tokens['user-a']}"},
        json={
            "default_location": "深圳湾",
            "default_task_type": "inspection",
            "default_start_time": "14:00",
            "default_end_time": "17:00",
        },
    ).status_code == 200

    monkeypatch.setattr("app.services.profile_memory.SessionLocal", api_session_factory)
    profile = get_or_create_user_profile("user-a")
    context = merge_profile_context(session_context=None, profile=profile)
    parsed = parse_natural_language_request("明天适合飞吗", context=context)

    assert parsed.context_used
    assert parsed.parsed["location"] == "深圳湾"
    assert parsed.parsed["task_type"] == "inspection"
    assert parsed.parsed["start_time"] == "14:00"
    assert parsed.parsed["end_time"] == "17:00"


def test_auto_profile_update_does_not_override_manual_defaults(
    api_client: TestClient,
    profile_tokens: dict[str, str],
    api_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert api_client.patch(
        "/users/me/profile",
        headers={"Authorization": f"Bearer {profile_tokens['user-a']}"},
        json={"default_location": "深圳湾", "default_task_type": "inspection"},
    ).status_code == 200

    monkeypatch.setattr("app.services.profile_memory.SessionLocal", api_session_factory)
    update_profile_from_parsed(
        user_id="user-a",
        parsed={"location": "广州塔", "task_type": "survey"},
    )

    response = api_client.get(
        "/users/me/profile",
        headers={"Authorization": f"Bearer {profile_tokens['user-a']}"},
    )
    payload = response.json()
    assert payload["default_location"] == "深圳湾"
    assert payload["default_task_type"] == "inspection"
    assert "广州塔" in payload["common_locations"]
    assert "survey" in payload["common_task_types"]
