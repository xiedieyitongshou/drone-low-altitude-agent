from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import RuleSet, User
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
                    role="admin",
                    is_active=True,
                ),
                User(
                    id="user-a",
                    username="user_a",
                    password_hash=hash_password("user123456"),
                    role="user",
                    is_active=True,
                ),
                User(
                    id="user-b",
                    username="user_b",
                    password_hash=hash_password("user123456"),
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


def valid_rule_set_payload(name: str = "用户巡航规则") -> dict:
    return {
        "name": name,
        "description": "测试规则集",
        "task_type": "cruise",
        "visibility": "private",
        "tenant_id": "public",
        "items": [
            {
                "metric": "wind_speed",
                "operator": ">=",
                "threshold_value": 25,
                "unit": "km/h",
                "decision": "禁飞",
                "label": "风速禁飞阈值",
                "risk_tag": "high_wind",
                "priority": 10,
                "enabled": True,
            },
            {
                "metric": "wind_speed",
                "operator": ">=",
                "threshold_value": 15,
                "unit": "km/h",
                "decision": "慎飞",
                "label": "风速慎飞阈值",
                "risk_tag": "wind_caution",
                "priority": 20,
                "enabled": True,
            },
        ],
    }


def test_user_can_create_validate_activate_and_list_own_rule_set() -> None:
    client, SessionLocal = build_test_client()
    try:
        create_response = client.post(
            "/rule-sets",
            json=valid_rule_set_payload(),
            headers=auth_headers("user-a"),
        )
        assert create_response.status_code == 201
        created = create_response.json()
        assert created["owner_user_id"] == "user-a"
        assert created["status"] == "draft"
        assert len(created["items"]) == 2

        rule_set_id = created["id"]
        validate_response = client.post(f"/rule-sets/{rule_set_id}/validate", headers=auth_headers("user-a"))
        assert validate_response.status_code == 200
        assert validate_response.json()["validation_errors"] == []

        activate_response = client.post(f"/rule-sets/{rule_set_id}/activate", headers=auth_headers("user-a"))
        assert activate_response.status_code == 200
        assert activate_response.json()["status"] == "active"

        list_response = client.get("/rule-sets", headers=auth_headers("user-a"))
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1

        with SessionLocal() as db:
            persisted = db.get(RuleSet, rule_set_id)
            assert persisted is not None
            assert persisted.status == "active"
    finally:
        app.dependency_overrides.clear()


def test_invalid_rule_set_can_be_saved_but_cannot_activate() -> None:
    client, _ = build_test_client()
    try:
        payload = valid_rule_set_payload()
        payload["items"][0]["threshold_value"] = 10
        payload["items"][1]["threshold_value"] = 20
        create_response = client.post("/rule-sets", json=payload, headers=auth_headers("user-a"))
        rule_set_id = create_response.json()["id"]

        validate_response = client.post(f"/rule-sets/{rule_set_id}/validate", headers=auth_headers("user-a"))
        assert validate_response.status_code == 200
        assert validate_response.json()["validation_errors"]

        activate_response = client.post(f"/rule-sets/{rule_set_id}/activate", headers=auth_headers("user-a"))
        assert activate_response.status_code == 409
        assert "errors" in activate_response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_user_cannot_read_or_modify_other_private_rule_set() -> None:
    client, _ = build_test_client()
    try:
        create_response = client.post(
            "/rule-sets",
            json=valid_rule_set_payload(),
            headers=auth_headers("user-a"),
        )
        rule_set_id = create_response.json()["id"]

        get_response = client.get(f"/rule-sets/{rule_set_id}", headers=auth_headers("user-b"))
        assert get_response.status_code == 404

        patch_response = client.patch(
            f"/rule-sets/{rule_set_id}",
            json={"name": "越权修改"},
            headers=auth_headers("user-b"),
        )
        assert patch_response.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_admin_can_create_and_activate_public_rule_set() -> None:
    client, _ = build_test_client()
    try:
        payload = valid_rule_set_payload("公共巡航规则")
        payload["visibility"] = "public"

        create_response = client.post("/rule-sets", json=payload, headers=auth_headers("admin-a"))
        assert create_response.status_code == 201
        rule_set_id = create_response.json()["id"]

        activate_response = client.post(f"/rule-sets/{rule_set_id}/activate", headers=auth_headers("admin-a"))
        assert activate_response.status_code == 200
        assert activate_response.json()["visibility"] == "public"

        user_list_response = client.get("/rule-sets", headers=auth_headers("user-a"))
        assert user_list_response.status_code == 200
        assert user_list_response.json()["total"] == 1

        user_patch_response = client.patch(
            f"/rule-sets/{rule_set_id}",
            json={"name": "普通用户不能改公共规则"},
            headers=auth_headers("user-a"),
        )
        assert user_patch_response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_rule_item_add_update_delete_flow() -> None:
    client, _ = build_test_client()
    try:
        create_response = client.post(
            "/rule-sets",
            json=valid_rule_set_payload(),
            headers=auth_headers("user-a"),
        )
        rule_set_id = create_response.json()["id"]

        add_response = client.post(
            f"/rule-sets/{rule_set_id}/items",
            json={
                "metric": "weather_text",
                "operator": "in",
                "threshold_values": ["雷雨", "暴雨"],
                "decision": "禁飞",
                "label": "高风险天气",
                "priority": 30,
                "enabled": True,
            },
            headers=auth_headers("user-a"),
        )
        assert add_response.status_code == 201
        added_item = add_response.json()["items"][-1]
        assert added_item["metric"] == "weather_text"

        patch_response = client.patch(
            f"/rule-sets/{rule_set_id}/items/{added_item['id']}",
            json={"label": "高风险天气禁飞", "priority": 5},
            headers=auth_headers("user-a"),
        )
        assert patch_response.status_code == 200
        patched_item = [item for item in patch_response.json()["items"] if item["id"] == added_item["id"]][0]
        assert patched_item["label"] == "高风险天气禁飞"
        assert patched_item["priority"] == 5

        delete_response = client.delete(
            f"/rule-sets/{rule_set_id}/items/{added_item['id']}",
            headers=auth_headers("user-a"),
        )
        assert delete_response.status_code == 200
        assert all(item["id"] != added_item["id"] for item in delete_response.json()["items"])
    finally:
        app.dependency_overrides.clear()
