from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    field: str | None = None
    message: str


class ErrorResponse(BaseModel):
    success: bool = False
    error_code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)
