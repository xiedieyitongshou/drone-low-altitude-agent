from pydantic import BaseModel, Field


class OrchestratorRequest(BaseModel):
    query: str = Field(..., min_length=2, description="自然语言任务请求")


class OrchestratorResponse(BaseModel):
    success: bool = True
    intent: str
    target_endpoint: str
    parsed: dict[str, object]
    message: str
    warnings: list[str] = Field(default_factory=list)
    result: dict[str, object] | None = None
    fallback: dict[str, object] | None = None
