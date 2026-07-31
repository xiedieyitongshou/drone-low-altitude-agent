import logging
import os
from typing import Any

from app.agent.state import AgentState
from app.agent.tools import ToolResult
from app.agent.trace import summarize_payload


logger = logging.getLogger("drone-low-altitude-agent.agent")


def is_raw_payload_logging_enabled() -> bool:
    return os.getenv("AGENT_LOG_RAW_PAYLOAD", "false").strip().lower() in {"1", "true", "yes", "on"}


def build_agent_log_context(
    *,
    event: str,
    state: AgentState | None = None,
    trace_id: str | None = None,
    run_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    tool_name: str | None = None,
    success: bool | None = None,
    latency_ms: int | None = None,
    error_code: str | None = None,
    status: str | None = None,
    plan_action: str | None = None,
    raw_payload: Any = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "event": event,
        "trace_id": trace_id or (state.trace_id if state else None),
        "run_id": run_id or (state.run_id if state else None),
        "user_id": user_id or (state.user_id if state else None),
        "session_id": session_id or (state.session_id if state else None),
        "tool_name": tool_name,
        "success": success,
        "latency_ms": latency_ms,
        "error_code": error_code,
        "status": status or (state.status.value if state else None),
        "plan_action": plan_action,
    }
    if raw_payload is not None:
        context["payload"] = summarize_payload(raw_payload) if is_raw_payload_logging_enabled() else summarize_for_log(raw_payload)
    if metadata:
        context["metadata"] = summarize_payload(metadata)
    return {key: value for key, value in context.items() if value is not None}


def summarize_for_log(payload: Any) -> Any:
    summary = summarize_payload(payload, max_string_length=80, max_list_items=5, max_dict_items=20)
    if isinstance(summary, str):
        return {"text_preview": summary, "text_length": len(str(payload))}
    return summary


def log_agent_event(level: int, message: str, **context: Any) -> None:
    logger.log(level, message, extra=build_agent_log_context(**context))
