from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import User
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


def test_register_cannot_create_admin() -> None:
    client, _ = build_test_client()
    try:
        response = client.post(
            "/auth/register",
            json={
                "username": "new_admin",
                "password": "password123",
                "display_name": "New Admin",
                "role": "admin",
            },
        )

        assert response.status_code == 201
        assert response.json()["role"] == "user"
    finally:
        app.dependency_overrides.clear()


def test_admin_users_requires_admin_role() -> None:
    client, _ = build_test_client()
    try:
        response = client.get("/admin/users", headers=auth_headers("user-a"))

        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_admin_can_list_filter_promote_and_disable_users() -> None:
    client, SessionLocal = build_test_client()
    try:
        list_response = client.get(
            "/admin/users?role=user&is_active=true",
            headers=auth_headers("admin-a"),
        )
        assert list_response.status_code == 200
        payload = list_response.json()
        assert payload["total"] == 2
        assert {item["username"] for item in payload["items"]} == {"user_a", "user_b"}

        role_response = client.patch(
            "/admin/users/user-a/role",
            json={"role": "admin"},
            headers=auth_headers("admin-a"),
        )
        assert role_response.status_code == 200
        assert role_response.json()["role"] == "admin"

        status_response = client.patch(
            "/admin/users/user-b/status",
            json={"is_active": False},
            headers=auth_headers("admin-a"),
        )
        assert status_response.status_code == 200
        assert status_response.json()["is_active"] is False

        with SessionLocal() as db:
            user_a = db.get(User, "user-a")
            user_b = db.get(User, "user-b")
            assert user_a is not None and user_a.role == "admin"
            assert user_b is not None and user_b.is_active is False

        me_response = client.get("/auth/me", headers=auth_headers("user-b"))
        assert me_response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_cannot_disable_or_downgrade_last_active_admin() -> None:
    client, _ = build_test_client()
    try:
        disable_response = client.patch(
            "/admin/users/admin-a/status",
            json={"is_active": False},
            headers=auth_headers("admin-a"),
        )
        assert disable_response.status_code == 409

        downgrade_response = client.patch(
            "/admin/users/admin-a/role",
            json={"role": "user"},
            headers=auth_headers("admin-a"),
        )
        assert downgrade_response.status_code == 409
    finally:
        app.dependency_overrides.clear()
