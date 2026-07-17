from pydantic import BaseModel, Field


class NaturalLanguageParseRequest(BaseModel):
    session_id: str | None = Field(default=None, description="会话 ID，用于上下文继承")
    query: str = Field(..., min_length=2, description="自然语言任务请求")


class NaturalLanguageParseResponse(BaseModel):
    session_id: str | None = None
    intent: str
    target_endpoint: str
    parsed: dict[str, object]
    context_used: bool = False
    warnings: list[str] = Field(default_factory=list)
