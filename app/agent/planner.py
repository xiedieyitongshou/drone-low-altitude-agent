from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.agent.business_routes import build_route_tool_input, get_business_route, normalize_business_intent, resolve_route_missing_fields
from app.agent.state import AgentState, AgentStatus
from app.agent.tools import ToolRegistry, default_tool_registry


class AgentPlanAction(StrEnum):
    ASK_CLARIFICATION = "ask_clarification"
    CALL_TOOL = "call_tool"
    RESPOND_DIRECTLY = "respond_directly"
    FALLBACK = "fallback"


class AgentPlan(BaseModel):
    action: AgentPlanAction
    reason: str
    tool_name: str | None = None
    tool_input: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def plan_next_step(
    state: AgentState,
    *,
    tool_registry: ToolRegistry = default_tool_registry,
) -> AgentPlan:
    if state.status == AgentStatus.COMPLETED:
        return AgentPlan(
            action=AgentPlanAction.RESPOND_DIRECTLY,
            reason="agent state is already completed",
        )

    if state.status == AgentStatus.FAILED:
        return AgentPlan(
            action=AgentPlanAction.FALLBACK,
            reason="agent state is failed and requires fallback response",
            metadata={"errors": state.errors},
        )

    if state.status == AgentStatus.TOOL_RUNNING:
        return AgentPlan(
            action=AgentPlanAction.FALLBACK,
            reason="agent state is already running a tool",
        )

    if state.status == AgentStatus.TOOL_COMPLETED:
        return AgentPlan(
            action=AgentPlanAction.RESPOND_DIRECTLY,
            reason="tool result exists and final response can be composed",
            metadata={"tool_results": list(state.tool_results.keys())},
        )

    missing_fields = _resolve_missing_fields(state)
    if state.status == AgentStatus.NEEDS_CLARIFICATION or missing_fields:
        return AgentPlan(
            action=AgentPlanAction.ASK_CLARIFICATION,
            reason="required fields are missing before tool planning",
            missing_fields=missing_fields,
        )

    intent = normalize_business_intent(state.current_intent)
    if intent is None:
        return AgentPlan(
            action=AgentPlanAction.FALLBACK,
            reason="intent is not available in agent state",
        )

    route = get_business_route(intent)
    if route is None:
        return AgentPlan(
            action=AgentPlanAction.FALLBACK,
            reason=f"unsupported intent: {intent}",
            metadata={"intent": intent},
        )
    tool_name = route.primary_tool

    if tool_name in state.tool_results:
        return AgentPlan(
            action=AgentPlanAction.RESPOND_DIRECTLY,
            reason=f"tool result already exists for intent: {intent}",
            metadata={"tool_name": tool_name},
        )

    try:
        tool_spec = tool_registry.get(tool_name).spec
    except Exception:
        return AgentPlan(
            action=AgentPlanAction.FALLBACK,
            reason=f"planned tool is not registered: {tool_name}",
            metadata={"intent": intent, "tool_name": tool_name},
        )

    return AgentPlan(
        action=AgentPlanAction.CALL_TOOL,
        tool_name=tool_name,
        tool_input=build_route_tool_input(route, state.task_draft),
        reason=f"intent={intent} is ready and maps to tool={tool_name}",
        metadata={
            "intent": intent,
            "route_kind": route.route_kind.value,
            "target_endpoint": route.target_endpoint,
            "side_effect": tool_spec.side_effect,
            "risk_level": tool_spec.risk_level,
        },
    )


def _resolve_missing_fields(state: AgentState) -> list[str]:
    explicit_missing_fields = [field for field in state.missing_fields if field]
    if explicit_missing_fields:
        return explicit_missing_fields

    intent = normalize_business_intent(state.current_intent)
    route = get_business_route(intent)
    if route is None:
        return []
    return resolve_route_missing_fields(route, state.task_draft)
