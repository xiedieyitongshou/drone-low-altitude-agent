from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent import TraceEventType, build_trace_event, summarize_payload
from app.db.base import Base
from app.services.agent_trace import list_trace_events, record_trace_event, record_trace_events


def build_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return TestingSessionLocal()


def test_summarize_payload_redacts_sensitive_fields_and_truncates_text():
    summary = summarize_payload(
        {
            "query": "深圳明天下午适合飞吗",
            "password": "secret-password",
            "nested": {"token": "secret-token"},
            "long_text": "a" * 250,
        }
    )

    assert summary["query"] == "深圳明天下午适合飞吗"
    assert summary["password"] == "[REDACTED]"
    assert summary["nested"]["token"] == "[REDACTED]"
    assert summary["long_text"] == f"{'a' * 200}..."


def test_build_trace_event_summarizes_input_and_output_payloads():
    event = build_trace_event(
        trace_id="trace-1",
        run_id="run-1",
        user_id="user-1",
        session_id="session-1",
        event_type=TraceEventType.TOOL_RESULT,
        step_index=2,
        status_before="tool_running",
        status_after="tool_completed",
        tool_name="retrieve_rag_advice",
        latency_ms=12,
        input_payload={"authorization": "Bearer abc", "task_type": "inspection"},
        output_payload={"snippets": [{"id": "k1"}]},
        metadata={"source": "unit-test"},
    )

    assert event.trace_id == "trace-1"
    assert event.event_type == TraceEventType.TOOL_RESULT
    assert event.input_summary["authorization"] == "[REDACTED]"
    assert event.input_summary["task_type"] == "inspection"
    assert event.output_summary == {"snippets": [{"id": "k1"}]}
    assert event.metadata == {"source": "unit-test"}


def test_record_trace_event_persists_event_to_database():
    with build_session() as db:
        event = build_trace_event(
            trace_id="trace-1",
            run_id="run-1",
            user_id="user-1",
            session_id="session-1",
            event_type=TraceEventType.PLAN,
            step_index=1,
            status_before="ready_to_plan",
            status_after="ready_to_plan",
            input_payload={"intent": "evaluate"},
            output_payload={"action": "call_tool"},
            message="planned next step",
        )

        record_id = record_trace_event(event, db=db)
        records = list_trace_events("trace-1", db=db)

        assert record_id == records[0].id
        assert records[0].trace_id == "trace-1"
        assert records[0].run_id == "run-1"
        assert records[0].event_type == "plan"
        assert records[0].input_summary_json == {"intent": "evaluate"}
        assert records[0].output_summary_json == {"action": "call_tool"}
        assert records[0].message == "planned next step"


def test_record_trace_events_preserves_step_order():
    with build_session() as db:
        events = [
            build_trace_event(
                trace_id="trace-1",
                run_id="run-1",
                event_type=TraceEventType.TOOL_RESULT,
                step_index=2,
                tool_name="evaluate_flight_risk",
            ),
            build_trace_event(
                trace_id="trace-1",
                run_id="run-1",
                event_type=TraceEventType.PLAN,
                step_index=1,
            ),
        ]

        record_ids = record_trace_events(events, db=db)
        records = list_trace_events("trace-1", db=db)

        assert len(record_ids) == 2
        assert [record.step_index for record in records] == [1, 2]
        assert [record.event_type for record in records] == ["plan", "tool_result"]
