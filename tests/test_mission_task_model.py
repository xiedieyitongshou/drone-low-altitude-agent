from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import AgentTraceEventRecord, ConversationRecord, CruiseAssessment, Location, MissionTask, TaskRequest, User
from app.schemas.mission_task import MissionTaskCreateRequest, MissionTaskStatusUpdateRequest
from app.services.mission_task_state import (
    MissionTaskStatus,
    MissionTaskStatusTransitionError,
    ensure_mission_task_status_transition,
)


def test_mission_task_model_can_aggregate_related_records() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    with TestingSessionLocal() as session:
        user = User(
            id="user-1",
            username="user_1",
            password_hash="hash",
            role="user",
            is_active=True,
        )
        task = MissionTask(
            id="task-1",
            user_id="user-1",
            title="Shenzhen Bay inspection",
            purpose="inspection",
            status=MissionTaskStatus.DRAFT.value,
            location_text="Shenzhen Bay",
            task_date="2026-08-18",
            start_time="14:00",
            end_time="16:00",
            task_type="inspection",
            candidate_locations_json=["Shenzhen Bay"],
            profile_context_json={"default_task_type": "inspection"},
        )
        location = Location(
            provider_name="qweather",
            provider_location_id="loc-1",
            name="Shenzhen Bay",
            latitude="22.5",
            longitude="113.9",
        )
        session.add_all([user, task, location])
        session.flush()
        session.add_all(
            [
                ConversationRecord(
                    conversation_id="conversation-1",
                    session_id="session-1",
                    user_id="user-1",
                    task_id="task-1",
                    query="evaluate this task",
                    success=True,
                ),
                TaskRequest(
                    request_id="request-1",
                    task_id="task-1",
                    request_type="evaluate",
                    location_text="Shenzhen Bay",
                    task_date="2026-08-18",
                    start_time="14:00",
                    end_time="16:00",
                    task_type="inspection",
                    raw_request_json={},
                ),
                CruiseAssessment(
                    request_id="request-1",
                    task_id="task-1",
                    location_id=location.id,
                    allow_cruise=True,
                    overall_decision="suitable",
                    summary_risk_factors_json=[],
                    rule_snapshot_json={},
                    rule_hits_json=[],
                ),
                AgentTraceEventRecord(
                    trace_id="trace-1",
                    run_id="run-1",
                    user_id="user-1",
                    session_id="session-1",
                    task_id="task-1",
                    event_type="plan",
                ),
            ]
        )
        session.commit()

        saved_task = session.get(MissionTask, "task-1")
        assert saved_task is not None
        assert saved_task.user_id == "user-1"
        assert saved_task.conversations[0].conversation_id == "conversation-1"
        assert saved_task.profile_context_json == {"default_task_type": "inspection"}

    columns_by_table = {
        table_name: {column["name"] for column in inspect(engine).get_columns(table_name)}
        for table_name in ["mission_tasks", "conversation_records", "task_requests", "cruise_assessments", "agent_trace_events"]
    }
    assert "selected_window_json" in columns_by_table["mission_tasks"]
    assert "latest_request_id" in columns_by_table["mission_tasks"]
    assert "task_id" in columns_by_table["conversation_records"]
    assert "task_id" in columns_by_table["task_requests"]
    assert "task_id" in columns_by_table["cruise_assessments"]
    assert "task_id" in columns_by_table["agent_trace_events"]


def test_mission_task_schemas_validate_status_and_task_type() -> None:
    payload = MissionTaskCreateRequest(
        title="Task",
        location="Shenzhen Bay",
        date="2026-08-18",
        start_time="14:00",
        end_time="16:00",
        task_type="inspection",
    )
    assert payload.task_type == "inspection"

    status_payload = MissionTaskStatusUpdateRequest(status="scheduled")
    assert status_payload.status == MissionTaskStatus.SCHEDULED


def test_mission_task_status_machine_rejects_terminal_transition() -> None:
    assert (
        ensure_mission_task_status_transition(MissionTaskStatus.DRAFT, MissionTaskStatus.EVALUATED)
        == MissionTaskStatus.EVALUATED
    )

    try:
        ensure_mission_task_status_transition(MissionTaskStatus.COMPLETED, MissionTaskStatus.SCHEDULED)
    except MissionTaskStatusTransitionError as exc:
        assert "completed -> scheduled" in str(exc)
    else:
        raise AssertionError("expected terminal status transition to be rejected")
