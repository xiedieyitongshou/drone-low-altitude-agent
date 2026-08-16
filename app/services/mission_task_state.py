from enum import StrEnum


class MissionTaskStatus(StrEnum):
    DRAFT = "draft"
    EVALUATED = "evaluated"
    SCHEDULED = "scheduled"
    RECHECK = "recheck"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


TERMINAL_MISSION_TASK_STATUSES = {
    MissionTaskStatus.COMPLETED,
    MissionTaskStatus.CANCELLED,
}

MISSION_TASK_STATUS_TRANSITIONS: dict[MissionTaskStatus, set[MissionTaskStatus]] = {
    MissionTaskStatus.DRAFT: {
        MissionTaskStatus.EVALUATED,
        MissionTaskStatus.SCHEDULED,
        MissionTaskStatus.CANCELLED,
    },
    MissionTaskStatus.EVALUATED: {
        MissionTaskStatus.DRAFT,
        MissionTaskStatus.SCHEDULED,
        MissionTaskStatus.CANCELLED,
    },
    MissionTaskStatus.SCHEDULED: {
        MissionTaskStatus.RECHECK,
        MissionTaskStatus.COMPLETED,
        MissionTaskStatus.CANCELLED,
    },
    MissionTaskStatus.RECHECK: {
        MissionTaskStatus.SCHEDULED,
        MissionTaskStatus.COMPLETED,
        MissionTaskStatus.CANCELLED,
    },
    MissionTaskStatus.COMPLETED: set(),
    MissionTaskStatus.CANCELLED: set(),
}


class MissionTaskStatusTransitionError(ValueError):
    pass


def normalize_mission_task_status(status: str | MissionTaskStatus) -> MissionTaskStatus:
    try:
        return status if isinstance(status, MissionTaskStatus) else MissionTaskStatus(status)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in MissionTaskStatus)
        raise MissionTaskStatusTransitionError(f"mission task status must be one of: {allowed}") from exc


def can_transition_mission_task_status(
    current_status: str | MissionTaskStatus,
    target_status: str | MissionTaskStatus,
) -> bool:
    current = normalize_mission_task_status(current_status)
    target = normalize_mission_task_status(target_status)
    if current == target:
        return True
    return target in MISSION_TASK_STATUS_TRANSITIONS[current]


def ensure_mission_task_status_transition(
    current_status: str | MissionTaskStatus,
    target_status: str | MissionTaskStatus,
) -> MissionTaskStatus:
    current = normalize_mission_task_status(current_status)
    target = normalize_mission_task_status(target_status)
    if not can_transition_mission_task_status(current, target):
        raise MissionTaskStatusTransitionError(
            f"invalid mission task status transition: {current.value} -> {target.value}"
        )
    return target
