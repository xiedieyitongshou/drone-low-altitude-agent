from pydantic import BaseModel, Field

from app.schemas.composed_response import UnifiedBusinessResponse


class OrchestratorRequest(BaseModel):
    session_id: str | None = Field(default=None, description='会话 ID，用于上下文继承')
    query: str = Field(..., min_length=2, description='自然语言任务请求')


class OrchestratorResponse(BaseModel):
    success: bool = True
    session_id: str | None = None
    intent: str
    target_endpoint: str
    parser_source: str = "rule"
    parsed: dict[str, object]
    context_used: bool = False
    message: str
    warnings: list[str] = Field(default_factory=list)
    composed: UnifiedBusinessResponse | None = None
    result: dict[str, object] | None = None
    fallback: dict[str, object] | None = None
