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
) -> MissionTaskResponse:
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
    db.commit()
    db.refresh(task)
    return to_mission_task_response(task)


def get_mission_task_detail(
    *,
    db: Session,
    current_user: User,
    task_id: str,
) -> MissionTaskDetailResponse:
    task = _get_visible_task(db=db, current_user=current_user, task_id=task_id)
    return to_mission_task_detail_response(db=db, task=task)


def update_mission_task(
    *,
    db: Session,
    current_user: User,
    task_id: str,
    payload: MissionTaskUpdateRequest,
) -> MissionTaskResponse:
    task = _get_owned_task(db=db, current_user=current_user, task_id=task_id)
    _ensure_not_terminal(task)

    values = payload.model_dump(exclude_unset=True)
    field_map = {
        "location": "location_text",
        "date": "task_date",
        "candidate_locations": "candidate_locations_json",
        "metadata": "metadata_json",
    }
    for field_name, value in values.items():
        model_field = field_map.get(field_name, field_name)
        if field_name in {"candidate_locations"} and value is not None:
            value = list(value)
        if field_name in {"metadata"} and value is not None:
            value = dict(value)
        setattr(task, model_field, value)

    task.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(task)
    return to_mission_task_response(task)


def update_mission_task_status(
    *,
    db: Session,
    current_user: User,
    task_id: str,
    payload: MissionTaskStatusUpdateRequest,
) -> MissionTaskResponse:
    task = _get_owned_task(db=db, current_user=current_user, task_id=task_id)
    target_status = ensure_mission_task_status_transition(task.status, payload.status)
    task.status = target_status.value
    task.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(task)
    return to_mission_task_response(task)


def to_mission_task_response(task: MissionTask) -> MissionTaskResponse:
    return MissionTaskResponse(
        id=task.id,
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
            .order_by(AgentTraceEventRecord.created_at.desc())
            .distinct()
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


def _get_visible_task(*, db: Session, current_user: User, task_id: str) -> MissionTask:
    task = db.get(MissionTask, task_id)
    if task is None:
        raise MissionTaskNotFoundError("mission task not found")
    if current_user.role != "admin" and task.user_id != current_user.id:
        raise MissionTaskNotFoundError("mission task not found")
    return task


def _get_owned_task(*, db: Session, current_user: User, task_id: str) -> MissionTask:
    task = _get_visible_task(db=db, current_user=current_user, task_id=task_id)
    if task.user_id != current_user.id:
        raise MissionTaskPermissionError("cannot modify another user's mission task")
    return task


def _ensure_not_terminal(task: MissionTask) -> None:
    status = normalize_mission_task_status(task.status)
    if status in TERMINAL_MISSION_TASK_STATUSES:
        raise MissionTaskLockedError("completed or cancelled mission tasks cannot be modified")
