from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import User
from app.dependencies import get_db
from app.services.auth_service import hash_password
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

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), TestingSessionLocal


def test_register_login_and_get_me() -> None:
    client, _ = build_test_client()
    try:
        register_response = client.post(
            "/auth/register",
            json={
                "username": "demo",
                "password": "demo123456",
                "display_name": "Demo User",
            },
        )
        assert register_response.status_code == 201
        registered = register_response.json()
        assert registered["username"] == "demo"
        assert registered["display_name"] == "Demo User"
        assert registered["role"] == "user"
        assert "password" not in registered
        assert "password_hash" not in registered

        login_response = client.post(
            "/auth/login",
            json={"username": "demo", "password": "demo123456"},
        )
        assert login_response.status_code == 200
        token_payload = login_response.json()
        assert token_payload["token_type"] == "bearer"
        assert token_payload["access_token"]

        me_response = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token_payload['access_token']}"},
        )
        assert me_response.status_code == 200
        assert me_response.json()["username"] == "demo"
    finally:
        app.dependency_overrides.clear()


def test_register_rejects_duplicate_username() -> None:
    client, _ = build_test_client()
    try:
        payload = {"username": "demo", "password": "demo123456"}
        assert client.post("/auth/register", json=payload).status_code == 201

        duplicate_response = client.post("/auth/register", json=payload)
        assert duplicate_response.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_login_rejects_wrong_password_and_disabled_user() -> None:
    client, SessionLocal = build_test_client()
    try:
        with SessionLocal() as db:
            db.add(
                User(
                    username="disabled",
                    password_hash=hash_password("demo123456"),
                    display_name="Disabled User",
                    role="user",
                    is_active=False,
                )
            )
            db.commit()

        wrong_password_response = client.post(
            "/auth/login",
            json={"username": "disabled", "password": "wrong-password"},
        )
        assert wrong_password_response.status_code == 401

        disabled_response = client.post(
            "/auth/login",
            json={"username": "disabled", "password": "demo123456"},
        )
        assert disabled_response.status_code == 403
    finally:
        app.dependency_overrides.clear()
