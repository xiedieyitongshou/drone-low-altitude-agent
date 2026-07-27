from pydantic import BaseModel, Field


class UserProfileResponse(BaseModel):
    user_id: str
    default_location: str | None = None
    default_task_type: str | None = None
    default_start_time: str | None = None
    default_end_time: str | None = None
    output_style: str | None = None
    common_locations: list[str] = Field(default_factory=list)
    common_task_types: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class UserProfileUpdateRequest(BaseModel):
    default_location: str | None = Field(default=None, max_length=255)
    default_task_type: str | None = Field(default=None, max_length=64)
    default_start_time: str | None = Field(default=None, max_length=32)
    default_end_time: str | None = Field(default=None, max_length=32)
    output_style: str | None = Field(default=None, max_length=64)
    common_locations: list[str] | None = None
    common_task_types: list[str] | None = None
