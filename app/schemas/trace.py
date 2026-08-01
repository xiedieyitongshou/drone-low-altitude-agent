from typing import Any

from pydantic import BaseModel, Field


TracePayload = dict[str, Any] | list[Any] | str | int | float | bool | None


class AgentTraceEventResponse(BaseModel):
    id: int
    trace_id: str
    run_id: str
    user_id: str | None = None
    session_id: str | None = None
    event_type: str
    step_index: int | None = None
    status_before: str | None = None
    status_after: str | None = None
    tool_name: str | None = None
    latency_ms: int | None = None
    input_summary: TracePayload = None
    output_summary: TracePayload = None
    error_code: str | None = None
    message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class AgentTraceDetailResponse(BaseModel):
    trace_id: str
    run_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    event_count: int
    events: list[AgentTraceEventResponse] = Field(default_factory=list)
