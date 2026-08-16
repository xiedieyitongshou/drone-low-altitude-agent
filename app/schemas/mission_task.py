from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.rules.mission_profiles import is_supported_task_type, normalize_task_type
from app.services.mission_task_state import MissionTaskStatus, normalize_mission_task_status


class MissionTaskBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., min_length=1, max_length=255)
    purpose: str | None = None
    location: str | None = Field(default=None, max_length=255)
    date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    task_type: str | None = None
    candidate_locations: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("task_type")
    @classmethod
    def validate_task_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_task_type(value)
        if not is_supported_task_type(normalized):
            raise ValueError("task_type must be one of: cruise, inspection, hover, survey")
        return normalized


class MissionTaskCreateRequest(MissionTaskBase):
    profile_context: dict[str, object] = Field(default_factory=dict)


class MissionTaskUpdateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=255)
    purpose: str | None = None
    location: str | None = Field(default=None, max_length=255)
    date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    task_type: str | None = None
    candidate_locations: list[str] | None = None
    metadata: dict[str, object] | None = None

    @field_validator("task_type")
    @classmethod
    def validate_task_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_task_type(value)
        if not is_supported_task_type(normalized):
            raise ValueError("task_type must be one of: cruise, inspection, hover, survey")
        return normalized


class MissionTaskStatusUpdateRequest(BaseModel):
    status: MissionTaskStatus

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, value: str | MissionTaskStatus) -> MissionTaskStatus:
        return normalize_mission_task_status(value)


class SelectedMissionWindow(BaseModel):
    start_time: str
    end_time: str
    rank: int | None = None
    decision: str | None = None
    reason: str | None = None
    source_request_id: str | None = None


class MissionTaskRecommendRequest(BaseModel):
    scan_hours: int = Field(default=72, ge=1, le=168)
    min_window_hours: int = Field(default=2, ge=1, le=24)


class MissionTaskSelectWindowRequest(BaseModel):
    rank: int | None = Field(default=None, ge=1)
    window: SelectedMissionWindow | None = None


class MissionTaskResponse(BaseModel):
    id: str
    user_id: str
    title: str
    purpose: str | None = None
    status: MissionTaskStatus
    location: str | None = None
    date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    task_type: str | None = None
    candidate_locations: list[str] = Field(default_factory=list)
    selected_window: dict[str, object] | None = None
    latest_decision: str | None = None
    latest_request_id: str | None = None
    latest_trace_id: str | None = None
    latest_conversation_id: str | None = None
    created_at: str
    updated_at: str


class MissionTaskListResponse(BaseModel):
    items: list[MissionTaskResponse] = Field(default_factory=list)
    page: int
    page_size: int
    total: int


class MissionTaskDetailResponse(MissionTaskResponse):
    profile_context: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)
    conversation_ids: list[str] = Field(default_factory=list)
    request_ids: list[str] = Field(default_factory=list)
    trace_ids: list[str] = Field(default_factory=list)
