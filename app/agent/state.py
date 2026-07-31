from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field

from app.agent.tools import ToolResult


class AgentStatus(StrEnum):
    INITIALIZED = "initialized"
    PARSED = "parsed"
    NEEDS_CLARIFICATION = "needs_clarification"
    READY_TO_PLAN = "ready_to_plan"
    TOOL_RUNNING = "tool_running"
    TOOL_COMPLETED = "tool_completed"
    FAILED = "failed"
    COMPLETED = "completed"


class AgentStep(BaseModel):
    step_index: int
    status: AgentStatus
    event: str
    tool_name: str | None = None
    tool_input: dict[str, object] | None = None
    tool_result: ToolResult | None = None
    state_delta: dict[str, object] = Field(default_factory=dict)
    message: str | None = None


class AgentState(BaseModel):
    query: str
    user_id: str | None = None
    session_id: str | None = None
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    status: AgentStatus = AgentStatus.INITIALIZED
    current_intent: str | None = None
    task_draft: dict[str, object] = Field(default_factory=dict)
    confirmed_fields: set[str] = Field(default_factory=set)
    missing_fields: list[str] = Field(default_factory=list)
    tool_results: dict[str, ToolResult] = Field(default_factory=dict)
    errors: list[dict[str, object]] = Field(default_factory=list)
    steps: list[AgentStep] = Field(default_factory=list)
    round_index: int = 0


def initialize_state(
    query: str,
    *,
    user_id: str | None = None,
    session_id: str | None = None,
) -> AgentState:
    state = AgentState(query=query, user_id=user_id, session_id=session_id)
    return _append_step(state, event="initialize", status=AgentStatus.INITIALIZED)


def merge_user_input(state: AgentState, updates: dict[str, object]) -> AgentState:
    task_draft = dict(state.task_draft)
    confirmed_fields = set(state.confirmed_fields)
    missing_fields = list(state.missing_fields)
    changed_fields: list[str] = []

    for field_name, value in updates.items():
        if value in (None, "", []):
            continue
        task_draft[field_name] = value
        confirmed_fields.add(field_name)
        changed_fields.append(field_name)
        if field_name in missing_fields:
            missing_fields.remove(field_name)

    return _append_step(
        state.model_copy(
            update={
                "task_draft": task_draft,
                "confirmed_fields": confirmed_fields,
                "missing_fields": missing_fields,
            }
        ),
        event="merge_user_input",
        status=state.status,
        state_delta={"changed_fields": changed_fields},
    )


def mark_parsed(
    state: AgentState,
    *,
    intent: str,
    parsed: dict[str, object],
    missing_fields: list[str] | None = None,
) -> AgentState:
    task_draft = dict(state.task_draft)
    confirmed_fields = set(state.confirmed_fields)

    for field_name, value in parsed.items():
        if value in (None, "", []):
            continue
        task_draft[field_name] = value
        confirmed_fields.add(field_name)

    next_missing_fields = list(missing_fields or [])
    next_status = AgentStatus.NEEDS_CLARIFICATION if next_missing_fields else AgentStatus.READY_TO_PLAN

    return _append_step(
        state.model_copy(
            update={
                "status": next_status,
                "current_intent": intent,
                "task_draft": task_draft,
                "confirmed_fields": confirmed_fields,
                "missing_fields": next_missing_fields,
            }
        ),
        event="parse",
        status=AgentStatus.PARSED,
        state_delta={
            "intent": intent,
            "parsed_fields": list(parsed.keys()),
            "missing_fields": next_missing_fields,
            "next_status": next_status.value,
        },
    )


def mark_needs_clarification(
    state: AgentState,
    missing_fields: list[str],
    *,
    message: str | None = None,
) -> AgentState:
    return _append_step(
        state.model_copy(
            update={
                "status": AgentStatus.NEEDS_CLARIFICATION,
                "missing_fields": list(missing_fields),
            }
        ),
        event="needs_clarification",
        status=AgentStatus.NEEDS_CLARIFICATION,
        state_delta={"missing_fields": list(missing_fields)},
        message=message,
    )


def mark_tool_running(
    state: AgentState,
    *,
    tool_name: str,
    tool_input: dict[str, object] | None = None,
) -> AgentState:
    return _append_step(
        state.model_copy(update={"status": AgentStatus.TOOL_RUNNING}),
        event="tool_running",
        status=AgentStatus.TOOL_RUNNING,
        tool_name=tool_name,
        tool_input=tool_input,
    )


def record_tool_result(
    state: AgentState,
    *,
    tool_name: str,
    tool_result: ToolResult,
) -> AgentState:
    tool_results = dict(state.tool_results)
    tool_results[tool_name] = tool_result
    errors = list(state.errors)
    next_status = AgentStatus.TOOL_COMPLETED

    if not tool_result.success:
        next_status = AgentStatus.FAILED
        errors.append(
            {
                "tool_name": tool_name,
                "error_code": tool_result.error_code,
                "message": tool_result.message,
            }
        )

    return _append_step(
        state.model_copy(
            update={
                "status": next_status,
                "tool_results": tool_results,
                "errors": errors,
            }
        ),
        event="tool_result",
        status=next_status,
        tool_name=tool_name,
        tool_result=tool_result,
        state_delta={
            "tool_name": tool_name,
            "success": tool_result.success,
            "error_code": tool_result.error_code,
        },
    )


def mark_completed(state: AgentState, *, message: str | None = None) -> AgentState:
    return _append_step(
        state.model_copy(update={"status": AgentStatus.COMPLETED}),
        event="complete",
        status=AgentStatus.COMPLETED,
        message=message,
    )


def mark_failed(
    state: AgentState,
    *,
    error_code: str,
    message: str,
) -> AgentState:
    errors = list(state.errors)
    errors.append({"error_code": error_code, "message": message})
    return _append_step(
        state.model_copy(update={"status": AgentStatus.FAILED, "errors": errors}),
        event="fail",
        status=AgentStatus.FAILED,
        state_delta={"error_code": error_code},
        message=message,
    )


def _append_step(
    state: AgentState,
    *,
    event: str,
    status: AgentStatus,
    tool_name: str | None = None,
    tool_input: dict[str, object] | None = None,
    tool_result: ToolResult | None = None,
    state_delta: dict[str, object] | None = None,
    message: str | None = None,
) -> AgentState:
    steps = list(state.steps)
    steps.append(
        AgentStep(
            step_index=len(steps) + 1,
            status=status,
            event=event,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_result=tool_result,
            state_delta=state_delta or {},
            message=message,
        )
    )
    return state.model_copy(update={"steps": steps, "round_index": len(steps)})
