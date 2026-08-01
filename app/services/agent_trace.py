from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AgentTraceEventRecord
from app.db.session import SessionLocal
from app.schemas.trace import AgentTraceDetailResponse, AgentTraceEventResponse

if TYPE_CHECKING:
    from app.agent.trace import TraceEvent


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


def get_user_trace_detail(
    *,
    db: Session,
    trace_id: str,
    user_id: str,
) -> AgentTraceDetailResponse | None:
    records = _list_user_trace_events(db=db, trace_id=trace_id, user_id=user_id)
    if not records:
        return None
    return _build_trace_detail(records)


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


def _list_user_trace_events(db: Session, trace_id: str, user_id: str) -> list[AgentTraceEventRecord]:
    return list(
        db.scalars(
            select(AgentTraceEventRecord)
            .where(AgentTraceEventRecord.trace_id == trace_id, AgentTraceEventRecord.user_id == user_id)
            .order_by(AgentTraceEventRecord.step_index.asc(), AgentTraceEventRecord.id.asc())
        ).all()
    )


def _build_trace_detail(records: list[AgentTraceEventRecord]) -> AgentTraceDetailResponse:
    first_record = records[0]
    return AgentTraceDetailResponse(
        trace_id=first_record.trace_id,
        run_id=first_record.run_id,
        user_id=first_record.user_id,
        session_id=first_record.session_id,
        event_count=len(records),
        events=[_build_trace_event_response(record) for record in records],
    )


def _build_trace_event_response(record: AgentTraceEventRecord) -> AgentTraceEventResponse:
    return AgentTraceEventResponse(
        id=record.id,
        trace_id=record.trace_id,
        run_id=record.run_id,
        user_id=record.user_id,
        session_id=record.session_id,
        event_type=record.event_type,
        step_index=record.step_index,
        status_before=record.status_before,
        status_after=record.status_after,
        tool_name=record.tool_name,
        latency_ms=record.latency_ms,
        input_summary=record.input_summary_json,
        output_summary=record.output_summary_json,
        error_code=record.error_code,
        message=record.message,
        metadata=record.metadata_json or {},
        created_at=record.created_at.isoformat(),
    )
