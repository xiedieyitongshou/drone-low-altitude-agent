from pydantic import BaseModel, Field


class NaturalLanguageParseRequest(BaseModel):
    query: str = Field(..., min_length=2, description="自然语言任务请求")


class NaturalLanguageParseResponse(BaseModel):
    intent: str
    target_endpoint: str
    parsed: dict[str, object]
    warnings: list[str] = Field(default_factory=list)

