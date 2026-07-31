from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.trace import TraceEvent
from app.db.models import AgentTraceEventRecord
from app.db.session import SessionLocal


def record_trace_event(event: TraceEvent, *, db: Session | None = None) -> int:
    if db is not None:
        record = _add_trace_event(db, event)
        db.commit()
        db.refresh(record)
        return record.id

    with SessionLocal() as session:
        record = _add_trace_event(session, event)
        session.commit()
        session.refresh(record)
        return record.id


def record_trace_events(events: Iterable[TraceEvent], *, db: Session | None = None) -> list[int]:
    if db is not None:
        records = [_add_trace_event(db, event) for event in events]
        db.commit()
        for record in records:
            db.refresh(record)
        return [record.id for record in records]

    with SessionLocal() as session:
        records = [_add_trace_event(session, event) for event in events]
        session.commit()
        for record in records:
            session.refresh(record)
        return [record.id for record in records]


def list_trace_events(trace_id: str, *, db: Session | None = None) -> list[AgentTraceEventRecord]:
    if db is not None:
        return _list_trace_events(db, trace_id)

    with SessionLocal() as session:
        return _list_trace_events(session, trace_id)


def _add_trace_event(db: Session, event: TraceEvent) -> AgentTraceEventRecord:
    record = AgentTraceEventRecord(
        trace_id=event.trace_id,
        run_id=event.run_id,
        user_id=event.user_id,
        session_id=event.session_id,
        event_type=event.event_type.value,
        step_index=event.step_index,
        status_before=event.status_before,
        status_after=event.status_after,
        tool_name=event.tool_name,
        latency_ms=event.latency_ms,
        input_summary_json=event.input_summary,
        output_summary_json=event.output_summary,
        error_code=event.error_code,
        message=event.message,
        metadata_json=event.metadata,
    )
    db.add(record)
    return record


def _list_trace_events(db: Session, trace_id: str) -> list[AgentTraceEventRecord]:
    return list(
        db.scalars(
            select(AgentTraceEventRecord)
            .where(AgentTraceEventRecord.trace_id == trace_id)
            .order_by(AgentTraceEventRecord.step_index.asc(), AgentTraceEventRecord.id.asc())
        ).all()
    )
