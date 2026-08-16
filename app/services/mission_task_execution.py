from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.agent.trace import TraceEventType, build_trace_event
from app.db.models import MissionTask, User
from app.schemas import (
    CruiseAssessmentResponse,
    CruiseEvaluateRequest,
    MissionTaskRecommendRequest,
    MissionTaskResponse,
    MissionTaskSelectWindowRequest,
    RecommendationRequest,
    RecommendationResponse,
)
from app.services.cruise_evaluator import evaluate_cruise_request_with_artifacts
from app.services.agent_trace import record_trace_events
from app.services.history_persistence import _persist_cruise_evaluation
from app.services.mission_task_management import (
    MissionTaskLockedError,
    MissionTaskNotFoundError,
    MissionTaskPermissionError,
    to_mission_task_response,
)
from app.services.mission_task_state import (
    MissionTaskStatus,
    TERMINAL_MISSION_TASK_STATUSES,
    ensure_mission_task_status_transition,
    normalize_mission_task_status,
)
from app.services.recommendation_executor import build_recommendation_response


class MissionTaskMissingFieldsError(ValueError):
    def __init__(self, missing_fields: list[str]) -> None:
        self.missing_fields = missing_fields
        super().__init__(f"mission task missing required fields: {', '.join(missing_fields)}")


class MissionTaskWindowSelectionError(ValueError):
    pass


def evaluate_mission_task(
    *,
    db: Session,
    current_user: User,
    task_id: str,
) -> CruiseAssessmentResponse:
    task = _get_owned_active_task(db=db, current_user=current_user, task_id=task_id)
    payload = _build_evaluation_request(task)
    artifacts = evaluate_cruise_request_with_artifacts(payload)
    request_id = _new_request_id()
    _persist_cruise_evaluation(
        session=db,
        request_id=request_id,
        payload=payload,
        artifacts=artifacts,
        task_id=task.id,
    )
    result = artifacts.response
    result.request["request_id"] = request_id
    result.request["task_id"] = task.id

    task.latest_request_id = request_id
    task.latest_decision = str(result.advice.overall_decision)
    task.status = ensure_mission_task_status_transition(task.status, MissionTaskStatus.EVALUATED).value
    task.updated_at = datetime.utcnow()
    db.commit()
    return result


def recommend_mission_task_windows(
    *,
    db: Session,
    current_user: User,
    task_id: str,
    payload: MissionTaskRecommendRequest,
) -> RecommendationResponse:
    task = _get_owned_active_task(db=db, current_user=current_user, task_id=task_id)
    request = _build_recommendation_request(task, payload)
    result = build_recommendation_response(request)
    result.request["task_id"] = task.id
    task.metadata_json = {
        **dict(task.metadata_json or {}),
        "latest_recommendation": result.model_dump(mode="json"),
    }
    task.updated_at = datetime.utcnow()
    db.commit()
    return result


def select_mission_task_window(
    *,
    db: Session,
    current_user: User,
    task_id: str,
    payload: MissionTaskSelectWindowRequest,
) -> MissionTaskResponse:
    task = _get_owned_active_task(db=db, current_user=current_user, task_id=task_id)
    selected_window = _resolve_selected_window(task=task, payload=payload)
    task.selected_window_json = selected_window
    task.status = ensure_mission_task_status_transition(task.status, MissionTaskStatus.SCHEDULED).value
    task.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(task)
    return to_mission_task_response(task)


def preflight_check_mission_task(
    *,
    db: Session,
    current_user: User,
    task_id: str,
) -> CruiseAssessmentResponse:
    task = _get_owned_active_task(db=db, current_user=current_user, task_id=task_id)
    previous_status = task.status
    payload = _build_preflight_request(task)
    artifacts = evaluate_cruise_request_with_artifacts(payload)
    request_id = _new_request_id()
    trace_id = uuid4().hex
    run_id = uuid4().hex
    _persist_cruise_evaluation(
        session=db,
        request_id=request_id,
        payload=payload,
        artifacts=artifacts,
        task_id=task.id,
        request_type="preflight_check",
    )
    result = artifacts.response
    result.request["request_id"] = request_id
    result.request["task_id"] = task.id
    result.request["request_type"] = "preflight_check"

    task.latest_request_id = request_id
    task.latest_trace_id = trace_id
    task.latest_decision = str(result.advice.overall_decision)
    task.status = ensure_mission_task_status_transition(task.status, MissionTaskStatus.RECHECK).value
    record_trace_events(
        [
            build_trace_event(
                trace_id=trace_id,
                run_id=run_id,
                user_id=current_user.id,
                event_type=TraceEventType.TOOL_CALL,
                step_index=1,
                status_before=previous_status,
                tool_name="preflight_check",
                input_payload=payload,
                metadata={"task_id": task.id, "request_type": "preflight_check"},
            ),
            build_trace_event(
                trace_id=trace_id,
                run_id=run_id,
                user_id=current_user.id,
                event_type=TraceEventType.TOOL_RESULT,
                step_index=2,
                status_after=task.status,
                tool_name="preflight_check",
                output_payload={
                    "request_id": request_id,
                    "decision": str(result.advice.overall_decision),
                    "risk_factors": list(result.advice.summary_risk_factors),
                },
                metadata={"task_id": task.id, "request_type": "preflight_check"},
            ),
            build_trace_event(
                trace_id=trace_id,
                run_id=run_id,
                user_id=current_user.id,
                event_type=TraceEventType.STATE_UPDATE,
                step_index=3,
                status_before=previous_status,
                status_after=task.status,
                output_payload={
                    "latest_request_id": request_id,
                    "latest_trace_id": trace_id,
                    "latest_decision": str(result.advice.overall_decision),
                },
                metadata={"task_id": task.id, "request_type": "preflight_check"},
            ),
        ],
        db=db,
        task_id=task.id,
        commit=False,
    )
    task.metadata_json = {
        **dict(task.metadata_json or {}),
        "latest_preflight_check": {
            "request_id": request_id,
            "trace_id": trace_id,
            "decision": str(result.advice.overall_decision),
            "checked_at": datetime.utcnow().isoformat(),
        },
    }
    task.updated_at = datetime.utcnow()
    db.commit()
    return result


def _get_owned_active_task(*, db: Session, current_user: User, task_id: str) -> MissionTask:
    task = db.get(MissionTask, task_id)
    if task is None:
        raise MissionTaskNotFoundError("mission task not found")
    if task.user_id != current_user.id:
        raise MissionTaskPermissionError("cannot operate another user's mission task")
    if normalize_mission_task_status(task.status) in TERMINAL_MISSION_TASK_STATUSES:
        raise MissionTaskLockedError("completed or cancelled mission tasks cannot run scheduling operations")
    return task


def _build_evaluation_request(task: MissionTask) -> CruiseEvaluateRequest:
    _ensure_task_fields(task, required_fields=["location_text", "task_date", "start_time", "end_time", "task_type"])
    return CruiseEvaluateRequest(
        location=str(task.location_text),
        date=str(task.task_date),
        start_time=str(task.start_time),
        end_time=str(task.end_time),
        task_type=str(task.task_type),
        purpose=task.purpose,
    )


def _build_recommendation_request(
    task: MissionTask,
    payload: MissionTaskRecommendRequest,
) -> RecommendationRequest:
    _ensure_task_fields(task, required_fields=["location_text", "task_date", "task_type"])
    return RecommendationRequest(
        location=str(task.location_text),
        date=str(task.task_date),
        task_type=str(task.task_type),
        purpose=task.purpose,
        scan_hours=payload.scan_hours,
        min_window_hours=payload.min_window_hours,
    )


def _build_preflight_request(task: MissionTask) -> CruiseEvaluateRequest:
    selected_window = task.selected_window_json if isinstance(task.selected_window_json, dict) else None
    if selected_window:
        start_time = selected_window.get("start_time")
        end_time = selected_window.get("end_time")
        if isinstance(start_time, str) and isinstance(end_time, str):
            parsed = _parse_selected_window_times(start_time=start_time, end_time=end_time)
            if parsed is not None:
                date_text, start_clock, end_clock = parsed
                _ensure_task_fields(task, required_fields=["location_text", "task_type"])
                return CruiseEvaluateRequest(
                    location=str(task.location_text),
                    date=date_text,
                    start_time=start_clock,
                    end_time=end_clock,
                    task_type=str(task.task_type),
                    purpose=task.purpose,
                )

    return _build_evaluation_request(task)


def _resolve_selected_window(*, task: MissionTask, payload: MissionTaskSelectWindowRequest) -> dict[str, object]:
    if payload.window is not None:
        return payload.window.model_dump(mode="json")

    if payload.rank is None:
        raise MissionTaskWindowSelectionError("rank or window must be provided")

    recommendation = dict(task.metadata_json or {}).get("latest_recommendation")
    if not isinstance(recommendation, dict):
        raise MissionTaskWindowSelectionError("no recommendation result is available for this mission task")

    recommendation_body = recommendation.get("recommendation")
    if not isinstance(recommendation_body, dict):
        raise MissionTaskWindowSelectionError("stored recommendation result is invalid")

    windows = recommendation_body.get("recommended_windows")
    if not isinstance(windows, list):
        raise MissionTaskWindowSelectionError("stored recommendation windows are invalid")

    for window in windows:
        if isinstance(window, dict) and window.get("rank") == payload.rank:
            return dict(window)
    raise MissionTaskWindowSelectionError(f"recommended window rank {payload.rank} not found")


def _ensure_task_fields(task: MissionTask, *, required_fields: list[str]) -> None:
    missing_fields = [field for field in required_fields if not getattr(task, field)]
    if missing_fields:
        field_aliases = {
            "location_text": "location",
            "task_date": "date",
        }
        raise MissionTaskMissingFieldsError([field_aliases.get(field, field) for field in missing_fields])


def _new_request_id() -> str:
    from uuid import uuid4

    return uuid4().hex


def _parse_selected_window_times(*, start_time: str, end_time: str) -> tuple[str, str, str] | None:
    try:
        start_dt = datetime.fromisoformat(start_time)
        end_dt = datetime.fromisoformat(end_time)
    except ValueError:
        return None

    return start_dt.date().isoformat(), start_dt.strftime("%H:%M"), end_dt.strftime("%H:%M")
