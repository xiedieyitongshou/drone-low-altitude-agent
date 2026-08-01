from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent import TraceEventType, build_trace_event
from app.db.base import Base
from app.db.models import User
from app.dependencies import get_db
from app.services.agent_trace import record_trace_events
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
        db.commit()
        record_trace_events(
            [
                build_trace_event(
                    trace_id="trace-a",
                    run_id="run-a",
                    user_id="user-a",
                    session_id="session-a",
                    event_type=TraceEventType.TOOL_RESULT,
                    step_index=2,
                    tool_name="evaluate_flight_risk",
                    input_payload={"authorization": "Bearer secret-token", "location": "深圳"},
                    output_payload={"risk_level": "low"},
                ),
                build_trace_event(
                    trace_id="trace-a",
                    run_id="run-a",
                    user_id="user-a",
                    session_id="session-a",
                    event_type=TraceEventType.PLAN,
                    step_index=1,
                    input_payload={"intent": "evaluate"},
                    output_payload={"action": "call_tool"},
                ),
                build_trace_event(
                    trace_id="trace-b",
                    run_id="run-b",
                    user_id="user-b",
                    session_id="session-b",
                    event_type=TraceEventType.ERROR,
                    step_index=1,
                    error_code="INTERNAL_ERROR",
                ),
            ],
            db=db,
        )

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


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_get_agent_trace_requires_login() -> None:
    client, _ = build_test_client()
    try:
        response = client.get("/agent/traces/trace-a")

        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_get_agent_trace_returns_current_user_events_in_step_order() -> None:
    client, tokens = build_test_client()
    try:
        response = client.get("/agent/traces/trace-a", headers=auth_headers(tokens["user-a"]))

        assert response.status_code == 200
        payload = response.json()
        assert payload["trace_id"] == "trace-a"
        assert payload["run_id"] == "run-a"
        assert payload["user_id"] == "user-a"
        assert payload["session_id"] == "session-a"
        assert payload["event_count"] == 2
        assert [event["step_index"] for event in payload["events"]] == [1, 2]
        assert [event["event_type"] for event in payload["events"]] == ["plan", "tool_result"]
        assert payload["events"][1]["input_summary"]["authorization"] == "[REDACTED]"
        assert payload["events"][1]["tool_name"] == "evaluate_flight_risk"
    finally:
        app.dependency_overrides.clear()


def test_get_agent_trace_hides_other_users_trace() -> None:
    client, tokens = build_test_client()
    try:
        response = client.get("/agent/traces/trace-b", headers=auth_headers(tokens["user-a"]))

        assert response.status_code == 404
        assert response.json()["detail"] == "trace not found"
    finally:
        app.dependency_overrides.clear()
