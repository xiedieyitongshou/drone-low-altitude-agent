from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import User, UserProfile
from app.dependencies import get_db
from app.services.auth_service import create_access_token, hash_password
from app.services.nl_parser import parse_natural_language_request
from app.services.profile_memory import get_or_create_user_profile, merge_profile_context, update_profile_from_parsed
from main import app


def build_test_client() -> tuple[TestClient, dict[str, str], sessionmaker[Session]]:
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
    }, TestingSessionLocal


def test_get_profile_creates_current_user_profile() -> None:
    client, tokens, _ = build_test_client()
    try:
        response = client.get(
            "/users/me/profile",
            headers={"Authorization": f"Bearer {tokens['user-a']}"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["user_id"] == "user-a"
        assert payload["default_task_type"] == "cruise"
        assert payload["common_task_types"] == ["cruise"]
    finally:
        app.dependency_overrides.clear()


def test_patch_profile_updates_only_current_user() -> None:
    client, tokens, SessionLocal = build_test_client()
    try:
        response = client.patch(
            "/users/me/profile",
            headers={"Authorization": f"Bearer {tokens['user-a']}"},
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

        with SessionLocal() as db:
            user_b_profile = db.scalar(select(UserProfile).where(UserProfile.user_id == "user-b"))
            assert user_b_profile is None
    finally:
        app.dependency_overrides.clear()


def test_profile_context_fills_missing_task_fields() -> None:
    client, tokens, SessionLocal = build_test_client()
    try:
        assert client.patch(
            "/users/me/profile",
            headers={"Authorization": f"Bearer {tokens['user-a']}"},
            json={
                "default_location": "深圳湾",
                "default_task_type": "inspection",
                "default_start_time": "14:00",
                "default_end_time": "17:00",
            },
        ).status_code == 200

        with patch_profile_session(SessionLocal):
            profile = get_or_create_user_profile("user-a")
            context = merge_profile_context(session_context=None, profile=profile)
            parsed = parse_natural_language_request("明天适合飞吗", context=context)

        assert parsed.context_used
        assert parsed.parsed["location"] == "深圳湾"
        assert parsed.parsed["task_type"] == "inspection"
        assert parsed.parsed["start_time"] == "14:00"
        assert parsed.parsed["end_time"] == "17:00"
    finally:
        app.dependency_overrides.clear()


def test_auto_profile_update_does_not_override_manual_defaults() -> None:
    client, tokens, SessionLocal = build_test_client()
    try:
        assert client.patch(
            "/users/me/profile",
            headers={"Authorization": f"Bearer {tokens['user-a']}"},
            json={"default_location": "深圳湾", "default_task_type": "inspection"},
        ).status_code == 200

        with patch_profile_session(SessionLocal):
            update_profile_from_parsed(
                user_id="user-a",
                parsed={"location": "广州塔", "task_type": "survey"},
            )

        response = client.get(
            "/users/me/profile",
            headers={"Authorization": f"Bearer {tokens['user-a']}"},
        )
        payload = response.json()
        assert payload["default_location"] == "深圳湾"
        assert payload["default_task_type"] == "inspection"
        assert "广州塔" in payload["common_locations"]
        assert "survey" in payload["common_task_types"]
    finally:
        app.dependency_overrides.clear()


class patch_profile_session:
    def __init__(self, SessionLocal: sessionmaker[Session]) -> None:
        self.SessionLocal = SessionLocal
        self.patch = None

    def __enter__(self):
        from unittest.mock import patch

        self.patch = patch("app.services.profile_memory.SessionLocal", self.SessionLocal)
        return self.patch.__enter__()

    def __exit__(self, exc_type, exc, traceback):
        return self.patch.__exit__(exc_type, exc, traceback)
