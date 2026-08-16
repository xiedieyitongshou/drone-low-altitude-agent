from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import MissionTask, User
from app.dependencies import get_db
from app.services.auth_service import create_access_token, hash_password
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
                    id="admin-a",
                    username="admin_a",
                    password_hash=hash_password("demo123456"),
                    role="admin",
                    is_active=True,
                ),
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
        "admin-a": create_access_token("admin-a"),
        "user-a": create_access_token("user-a"),
        "user-b": create_access_token("user-b"),
    }, TestingSessionLocal


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def valid_task_payload(title: str = "Shenzhen Bay inspection") -> dict:
    return {
        "title": title,
        "purpose": "preflight inspection",
        "location": "Shenzhen Bay",
        "date": "2026-08-18",
        "start_time": "14:00",
        "end_time": "16:00",
        "task_type": "inspection",
        "candidate_locations": ["Shenzhen Bay", "Nanshan"],
        "profile_context": {"default_task_type": "inspection"},
        "metadata": {"source": "api-test"},
    }


def test_user_can_create_list_get_and_patch_own_task() -> None:
    client, tokens, SessionLocal = build_test_client()
    try:
        create_response = client.post(
            "/tasks",
            json=valid_task_payload(),
            headers=auth_headers(tokens["user-a"]),
        )
        assert create_response.status_code == 201
        created = create_response.json()
        assert created["user_id"] == "user-a"
        assert created["status"] == "draft"
        assert created["location"] == "Shenzhen Bay"
        assert created["candidate_locations"] == ["Shenzhen Bay", "Nanshan"]
        task_id = created["id"]

        list_response = client.get("/tasks", headers=auth_headers(tokens["user-a"]))
        assert list_response.status_code == 200
        listed = list_response.json()
        assert listed["total"] == 1
        assert listed["items"][0]["id"] == task_id

        get_response = client.get(f"/tasks/{task_id}", headers=auth_headers(tokens["user-a"]))
        assert get_response.status_code == 200
        detail = get_response.json()
        assert detail["id"] == task_id
        assert detail["profile_context"] == {"default_task_type": "inspection"}
        assert detail["metadata"] == {"source": "api-test"}

        patch_response = client.patch(
            f"/tasks/{task_id}",
            json={"title": "Updated task", "task_type": "survey"},
            headers=auth_headers(tokens["user-a"]),
        )
        assert patch_response.status_code == 200
        assert patch_response.json()["title"] == "Updated task"
        assert patch_response.json()["task_type"] == "survey"

        with SessionLocal() as db:
            persisted = db.get(MissionTask, task_id)
            assert persisted is not None
            assert persisted.title == "Updated task"
            assert persisted.task_type == "survey"
    finally:
        app.dependency_overrides.clear()


def test_user_cannot_read_or_modify_another_users_task() -> None:
    client, tokens, _ = build_test_client()
    try:
        create_response = client.post(
            "/tasks",
            json=valid_task_payload(),
            headers=auth_headers(tokens["user-a"]),
        )
        task_id = create_response.json()["id"]

        get_response = client.get(f"/tasks/{task_id}", headers=auth_headers(tokens["user-b"]))
        assert get_response.status_code == 404

        patch_response = client.patch(
            f"/tasks/{task_id}",
            json={"title": "illegal update"},
            headers=auth_headers(tokens["user-b"]),
        )
        assert patch_response.status_code == 404

        status_response = client.patch(
            f"/tasks/{task_id}/status",
            json={"status": "cancelled"},
            headers=auth_headers(tokens["user-b"]),
        )
        assert status_response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_status_transition_and_terminal_task_locking() -> None:
    client, tokens, _ = build_test_client()
    try:
        create_response = client.post(
            "/tasks",
            json=valid_task_payload(),
            headers=auth_headers(tokens["user-a"]),
        )
        task_id = create_response.json()["id"]

        evaluated_response = client.patch(
            f"/tasks/{task_id}/status",
            json={"status": "evaluated"},
            headers=auth_headers(tokens["user-a"]),
        )
        assert evaluated_response.status_code == 200
        assert evaluated_response.json()["status"] == "evaluated"

        completed_response = client.patch(
            f"/tasks/{task_id}/status",
            json={"status": "completed"},
            headers=auth_headers(tokens["user-a"]),
        )
        assert completed_response.status_code == 409

        scheduled_response = client.patch(
            f"/tasks/{task_id}/status",
            json={"status": "scheduled"},
            headers=auth_headers(tokens["user-a"]),
        )
        assert scheduled_response.status_code == 200

        completed_response = client.patch(
            f"/tasks/{task_id}/status",
            json={"status": "completed"},
            headers=auth_headers(tokens["user-a"]),
        )
        assert completed_response.status_code == 200
        assert completed_response.json()["status"] == "completed"

        patch_response = client.patch(
            f"/tasks/{task_id}",
            json={"title": "should be locked"},
            headers=auth_headers(tokens["user-a"]),
        )
        assert patch_response.status_code == 409

        reopen_response = client.patch(
            f"/tasks/{task_id}/status",
            json={"status": "scheduled"},
            headers=auth_headers(tokens["user-a"]),
        )
        assert reopen_response.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_admin_can_audit_task_list_and_detail() -> None:
    client, tokens, _ = build_test_client()
    try:
        create_response = client.post(
            "/tasks",
            json=valid_task_payload(),
            headers=auth_headers(tokens["user-a"]),
        )
        task_id = create_response.json()["id"]

        list_response = client.get("/tasks", headers=auth_headers(tokens["admin-a"]))
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1

        filtered_response = client.get(
            "/tasks?user_id=user-a",
            headers=auth_headers(tokens["admin-a"]),
        )
        assert filtered_response.status_code == 200
        assert filtered_response.json()["items"][0]["id"] == task_id

        detail_response = client.get(f"/tasks/{task_id}", headers=auth_headers(tokens["admin-a"]))
        assert detail_response.status_code == 200
        assert detail_response.json()["user_id"] == "user-a"

        patch_response = client.patch(
            f"/tasks/{task_id}",
            json={"title": "admin should not mutate audited task"},
            headers=auth_headers(tokens["admin-a"]),
        )
        assert patch_response.status_code == 403
    finally:
        app.dependency_overrides.clear()
