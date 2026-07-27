from pydantic import BaseModel, Field


class ConversationSummary(BaseModel):
    conversation_id: str
    session_id: str | None = None
    query: str
    intent: str | None = None
    target_endpoint: str | None = None
    parser_source: str | None = None
    success: bool
    message: str | None = None
    created_at: str


class ConversationListResponse(BaseModel):
    items: list[ConversationSummary] = Field(default_factory=list)
    page: int
    page_size: int
    total: int


class ConversationDetailResponse(ConversationSummary):
    parsed: dict[str, object] | None = None
    context_used: bool = False
    explanation: str | None = None
    response: dict[str, object] | None = None
