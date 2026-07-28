from datetime import datetime

from pydantic import BaseModel, Field


class AdminUserResponse(BaseModel):
    id: str
    username: str
    display_name: str | None = None
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AdminUserListResponse(BaseModel):
    items: list[AdminUserResponse]
    page: int
    page_size: int
    total: int


class AdminUserStatusUpdateRequest(BaseModel):
    is_active: bool


class AdminUserRoleUpdateRequest(BaseModel):
    role: str = Field(..., pattern="^(user|admin)$")


class AdminConversationSummary(BaseModel):
    conversation_id: str
    session_id: str | None = None
    user_id: str
    username: str | None = None
    display_name: str | None = None
    query: str
    intent: str | None = None
    target_endpoint: str | None = None
    parser_source: str | None = None
    success: bool
    message: str | None = None
    created_at: str


class AdminConversationListResponse(BaseModel):
    items: list[AdminConversationSummary] = Field(default_factory=list)
    page: int
    page_size: int
    total: int


class AdminConversationDetailResponse(AdminConversationSummary):
    parsed: dict[str, object] | None = None
    context_used: bool = False
    explanation: str | None = None
    response: dict[str, object] | None = None


class AdminTaskStatsResponse(BaseModel):
    total_users: int
    active_users: int
    disabled_users: int
    admin_users: int
    total_tasks: int
    successful_tasks: int
    failed_tasks: int
    high_risk_tasks: int
    rule_rejected_tasks: int
    parser_failed_tasks: int
