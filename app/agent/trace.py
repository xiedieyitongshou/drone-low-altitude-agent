from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TraceEventType(StrEnum):
    PLAN = "plan"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    STATE_UPDATE = "state_update"
    FALLBACK = "fallback"
    FINAL_RESPONSE = "final_response"
    ERROR = "error"


SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "credential",
    "email",
    "id_card",
    "jwt",
    "key",
    "mobile",
    "password",
    "phone",
    "refresh_token",
    "secret",
    "token",
}


class TraceEvent(BaseModel):
    trace_id: str
    run_id: str
    event_type: TraceEventType
    step_index: int | None = None
    user_id: str | None = None
    session_id: str | None = None
    status_before: str | None = None
    status_after: str | None = None
    tool_name: str | None = None
    latency_ms: int | None = None
    input_summary: dict[str, Any] | list[Any] | str | int | float | bool | None = None
    output_summary: dict[str, Any] | list[Any] | str | int | float | bool | None = None
    error_code: str | None = None
    message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def build_trace_event(
    *,
    trace_id: str,
    run_id: str,
    event_type: TraceEventType,
    step_index: int | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    status_before: str | None = None,
    status_after: str | None = None,
    tool_name: str | None = None,
    latency_ms: int | None = None,
    input_payload: Any = None,
    output_payload: Any = None,
    error_code: str | None = None,
    message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> TraceEvent:
    return TraceEvent(
        trace_id=trace_id,
        run_id=run_id,
        event_type=event_type,
        step_index=step_index,
        user_id=user_id,
        session_id=session_id,
        status_before=status_before,
        status_after=status_after,
        tool_name=tool_name,
        latency_ms=latency_ms,
        input_summary=summarize_payload(input_payload),
        output_summary=summarize_payload(output_payload),
        error_code=error_code,
        message=message,
        metadata=summarize_payload(metadata or {}),
    )


def summarize_payload(
    payload: Any,
    *,
    max_string_length: int = 200,
    max_list_items: int = 10,
    max_dict_items: int = 30,
) -> Any:
    if payload is None or isinstance(payload, bool | int | float):
        return payload
    if isinstance(payload, str):
        return _truncate(payload, max_string_length)
    if isinstance(payload, BaseModel):
        return summarize_payload(
            payload.model_dump(mode="json"),
            max_string_length=max_string_length,
            max_list_items=max_list_items,
            max_dict_items=max_dict_items,
        )
    if isinstance(payload, dict):
        summary: dict[str, Any] = {}
        for index, (key, value) in enumerate(payload.items()):
            if index >= max_dict_items:
                summary["_truncated"] = True
                break
            key_text = str(key)
            if key_text.lower() in SENSITIVE_KEYS:
                summary[key_text] = "[REDACTED]"
                continue
            summary[key_text] = summarize_payload(
                value,
                max_string_length=max_string_length,
                max_list_items=max_list_items,
                max_dict_items=max_dict_items,
            )
        return summary
    if isinstance(payload, list | tuple | set):
        items = list(payload)
        summary = [
            summarize_payload(
                item,
                max_string_length=max_string_length,
                max_list_items=max_list_items,
                max_dict_items=max_dict_items,
            )
            for item in items[:max_list_items]
        ]
        if len(items) > max_list_items:
            summary.append({"_truncated": True, "remaining": len(items) - max_list_items})
        return summary
    return _truncate(str(payload), max_string_length)


def _truncate(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return f"{value[:max_length]}..."
