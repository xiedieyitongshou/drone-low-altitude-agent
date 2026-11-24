from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import AgentTraceEventRecord, ConversationRecord, CruiseAssessment, MissionTask, TaskRequest, User
from app.schemas import (
    MissionTaskCreateRequest,
    MissionTaskDetailResponse,
    MissionTaskListResponse,
    MissionTaskResponse,
    MissionTaskStatusUpdateRequest,
    MissionTaskUpdateRequest,
)
from app.services.mission_task_state import (
    MissionTaskStatus,
    MissionTaskStatusTransitionError,
    TERMINAL_MISSION_TASK_STATUSES,
    ensure_mission_task_status_transition,
    normalize_mission_task_status,
)
from app.services.idempotency import TASK_CREATE, claim_operation
from app.services.mission_task_versioning import check_task_version, task_write_transaction


class MissionTaskNotFoundError(Exception):
    pass


class MissionTaskPermissionError(Exception):
    pass


class MissionTaskLockedError(Exception):
    pass


def list_mission_tasks(
    *,
    db: Session,
    current_user: User,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    keyword: str | None = None,
    user_id: str | None = None,
) -> MissionTaskListResponse:
    safe_page = max(page, 1)
    safe_page_size = min(max(page_size, 1), 100)
    filters = []

    if current_user.role == "admin":
        if user_id:
            filters.append(MissionTask.user_id == user_id)
    else:
        filters.append(MissionTask.user_id == current_user.id)

    if status:
        filters.append(MissionTask.status == normalize_mission_task_status(status).value)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        if pattern != "%%":
            filters.append(or_(MissionTask.title.like(pattern), MissionTask.purpose.like(pattern)))

    count_statement = select(func.count()).select_from(MissionTask)
    list_statement = select(MissionTask).order_by(MissionTask.updated_at.desc(), MissionTask.created_at.desc())
    if filters:
        count_statement = count_statement.where(*filters)
        list_statement = list_statement.where(*filters)

    total = db.scalar(count_statement) or 0
    tasks = db.scalars(
        list_statement.offset((safe_page - 1) * safe_page_size).limit(safe_page_size)
    ).all()
    return MissionTaskListResponse(
        items=[to_mission_task_response(task) for task in tasks],
        page=safe_page,
        page_size=safe_page_size,
        total=total,
    )


def create_mission_task(
    *,
    db: Session,
    current_user: User,
    payload: MissionTaskCreateRequest,
    idempotency_key: str | None = None,
    operation: str = TASK_CREATE,
) -> MissionTaskResponse:
    if idempotency_key is not None:
        try:
            receipt = claim_operation(
                db=db, user_id=current_user.id, operation=operation,
                key=idempotency_key, payload=payload.model_dump(mode="json"),
            )
            if receipt.response_json is not None:
                response = MissionTaskResponse.model_validate(receipt.response_json)
                db.commit()
                return response
            response = _insert_mission_task(db=db, current_user=current_user, payload=payload)
            receipt.response_json = response.model_dump(mode="json")
            db.commit()
            return response
        except Exception:
            db.rollback()
            raise
    response = _insert_mission_task(db=db, current_user=current_user, payload=payload)
    db.commit()
    return response


def _insert_mission_task(*, db: Session, current_user: User, payload: MissionTaskCreateRequest) -> MissionTaskResponse:
    task = MissionTask(
        user_id=current_user.id,
        title=payload.title,
        purpose=payload.purpose,
        status=MissionTaskStatus.DRAFT.value,
        location_text=payload.location,
        task_date=payload.date,
        start_time=payload.start_time,
        end_time=payload.end_time,
        task_type=payload.task_type,
        candidate_locations_json=list(payload.candidate_locations),
        profile_context_json=dict(payload.profile_context),
        metadata_json=dict(payload.metadata),
    )
    db.add(task)
    db.flush()
    return to_mission_task_response(task)


def get_mission_task_detail(
    *,
    db: Session,
    current_user: User,
    task_id: str,
) -> MissionTaskDetailResponse:
    task = get_visible_mission_task(db=db, current_user=current_user, task_id=task_id)
    return to_mission_task_detail_response(db=db, task=task)


def update_mission_task(
    *,
    db: Session,
    current_user: User,
    task_id: str,
    payload: MissionTaskUpdateRequest,
) -> MissionTaskResponse:
    with task_write_transaction(db):
        task = _get_owned_task(db=db, current_user=current_user, task_id=task_id)
        check_task_version(task, payload.expected_version)
        _ensure_not_terminal(task)
        values = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
        reserved_metadata = {
            key: value for key, value in dict(task.metadata_json or {}).items()
            if key in {"latest_recommendation", "latest_preflight_check"}
        }
        field_map = {
            "location": "location_text", "date": "task_date",
            "candidate_locations": "candidate_locations_json", "metadata": "metadata_json",
        }
        critical_fields = {"location", "date", "start_time", "end_time", "task_type", "purpose", "candidate_locations"}
        invalidates_results = any(
            name in critical_fields and value != getattr(task, field_map.get(name, name))
            for name, value in values.items()
        )
        for field_name, value in values.items():
            setattr(task, field_map.get(field_name, field_name), value)
        if invalidates_results:
            task.status = ensure_mission_task_status_transition(task.status, MissionTaskStatus.DRAFT).value
            invalidate_current_task_results(task)
        # These are server-owned artifacts, not writable user metadata.
        if invalidates_results or "metadata" in values:
            metadata = dict(task.metadata_json or {})
            for key in ("latest_recommendation", "latest_preflight_check"):
                metadata.pop(key, None)
            if not invalidates_results:
                metadata.update(reserved_metadata)
            task.metadata_json = metadata
        task.updated_at = datetime.utcnow()
        db.flush()
        return to_mission_task_response(task)


def update_mission_task_status(
    *,
    db: Session,
    current_user: User,
    task_id: str,
    payload: MissionTaskStatusUpdateRequest,
) -> MissionTaskResponse:
    with task_write_transaction(db):
        task = _get_owned_task(db=db, current_user=current_user, task_id=task_id)
        # A repeated cancellation acknowledges an already achieved terminal state.
        if task.status == MissionTaskStatus.CANCELLED.value and payload.status == MissionTaskStatus.CANCELLED:
            return to_mission_task_response(task)
        check_task_version(task, payload.expected_version)
        target_status = ensure_mission_task_status_transition(task.status, payload.status)
        task.status = target_status.value
        if target_status == MissionTaskStatus.DRAFT:
            invalidate_current_task_results(task)
        task.updated_at = datetime.utcnow()
        db.flush()
        return to_mission_task_response(task)


def invalidate_current_task_results(task: MissionTask) -> None:
    task.latest_request_id = None
    task.latest_trace_id = None
    task.latest_conversation_id = None
    task.latest_decision = None
    task.selected_window_json = None
    metadata = dict(task.metadata_json or {})
    metadata.pop("latest_recommendation", None)
    metadata.pop("latest_preflight_check", None)
    task.metadata_json = metadata


def to_mission_task_response(task: MissionTask) -> MissionTaskResponse:
    return MissionTaskResponse(
        id=task.id,
        version=task.version,
        user_id=task.user_id,
        title=task.title,
        purpose=task.purpose,
        status=normalize_mission_task_status(task.status),
        location=task.location_text,
        date=task.task_date,
        start_time=task.start_time,
        end_time=task.end_time,
        task_type=task.task_type,
        candidate_locations=list(task.candidate_locations_json or []),
        selected_window=task.selected_window_json,
        latest_decision=task.latest_decision,
        latest_request_id=task.latest_request_id,
        latest_trace_id=task.latest_trace_id,
        latest_conversation_id=task.latest_conversation_id,
        created_at=task.created_at.isoformat(),
        updated_at=task.updated_at.isoformat(),
    )


def to_mission_task_detail_response(*, db: Session, task: MissionTask) -> MissionTaskDetailResponse:
    base = to_mission_task_response(task)
    conversation_ids = list(
        db.scalars(
            select(ConversationRecord.conversation_id)
            .where(ConversationRecord.task_id == task.id)
            .order_by(ConversationRecord.created_at.desc())
        ).all()
    )
    request_ids = list(
        db.scalars(
            select(TaskRequest.request_id)
            .where(TaskRequest.task_id == task.id)
            .order_by(TaskRequest.created_at.desc())
        ).all()
    )
    trace_ids = list(
        db.scalars(
            select(AgentTraceEventRecord.trace_id)
            .where(AgentTraceEventRecord.task_id == task.id)
            .group_by(AgentTraceEventRecord.trace_id)
            .order_by(
                func.max(AgentTraceEventRecord.created_at).desc(),
                AgentTraceEventRecord.trace_id.asc(),
            )
        ).all()
    )
    assessment_request_ids = list(
        db.scalars(
            select(CruiseAssessment.request_id)
            .where(CruiseAssessment.task_id == task.id)
            .order_by(CruiseAssessment.created_at.desc())
        ).all()
    )
    merged_request_ids = list(dict.fromkeys([*request_ids, *assessment_request_ids]))
    return MissionTaskDetailResponse(
        **base.model_dump(),
        profile_context=dict(task.profile_context_json or {}),
        metadata=dict(task.metadata_json or {}),
        conversation_ids=conversation_ids,
        request_ids=merged_request_ids,
        trace_ids=trace_ids,
    )


def get_visible_mission_task(*, db: Session, current_user: User, task_id: str) -> MissionTask:
    task = db.get(MissionTask, task_id)
    if task is None:
        raise MissionTaskNotFoundError("mission task not found")
    if current_user.role != "admin" and task.user_id != current_user.id:
        raise MissionTaskNotFoundError("mission task not found")
    return task


def _get_owned_task(*, db: Session, current_user: User, task_id: str) -> MissionTask:
    task = get_visible_mission_task(db=db, current_user=current_user, task_id=task_id)
    if task.user_id != current_user.id:
        raise MissionTaskPermissionError("cannot modify another user's mission task")
    return task


def _ensure_not_terminal(task: MissionTask) -> None:
    status = normalize_mission_task_status(task.status)
    if status in TERMINAL_MISSION_TASK_STATUSES:
        raise MissionTaskLockedError("completed or cancelled mission tasks cannot be modified")
