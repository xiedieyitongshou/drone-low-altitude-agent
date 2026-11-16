from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import User
from app.services.auth_service import hash_password


def test_register_login_and_get_me(api_client: TestClient) -> None:
    register_response = api_client.post(
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

    login_response = api_client.post(
        "/auth/login",
        json={"username": "demo", "password": "demo123456"},
    )
    assert login_response.status_code == 200
    token_payload = login_response.json()
    assert token_payload["token_type"] == "bearer"
    assert token_payload["access_token"]

    me_response = api_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token_payload['access_token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["username"] == "demo"


def test_register_rejects_duplicate_username(api_client: TestClient) -> None:
    payload = {"username": "demo", "password": "demo123456"}
    assert api_client.post("/auth/register", json=payload).status_code == 201

    duplicate_response = api_client.post("/auth/register", json=payload)
    assert duplicate_response.status_code == 409


def test_login_rejects_wrong_password_and_disabled_user(
    api_client: TestClient, api_session_factory: sessionmaker[Session]
) -> None:
    with api_session_factory() as db:
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

    wrong_password_response = api_client.post(
        "/auth/login",
        json={"username": "disabled", "password": "wrong-password"},
    )
    assert wrong_password_response.status_code == 401

    disabled_response = api_client.post(
        "/auth/login",
        json={"username": "disabled", "password": "demo123456"},
    )
    assert disabled_response.status_code == 403
