from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

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


INTENT_TOOL_MAPPING: dict[str, str] = {
    "evaluate": "evaluate_flight_risk",
    "recommend": "recommend_flight_windows",
    "compare": "compare_flight_locations",
    "knowledge": "retrieve_rag_advice",
    "rag": "retrieve_rag_advice",
    "advice": "retrieve_rag_advice",
    "explain": "retrieve_rag_advice",
    "history": "query_user_history",
    "query_history": "query_user_history",
}

INTENT_REQUIRED_FIELDS: dict[str, list[str]] = {
    "evaluate": ["location", "date", "start_time", "end_time", "task_type"],
    "recommend": ["location", "date", "task_type"],
    "compare": ["locations", "date", "start_time", "end_time", "task_type"],
    "knowledge": ["task_type"],
    "rag": ["task_type"],
    "advice": ["task_type"],
    "explain": ["task_type"],
    "history": [],
    "query_history": [],
}


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

    intent = _normalize_intent(state.current_intent)
    if intent is None:
        return AgentPlan(
            action=AgentPlanAction.FALLBACK,
            reason="intent is not available in agent state",
        )

    tool_name = INTENT_TOOL_MAPPING.get(intent)
    if tool_name is None:
        return AgentPlan(
            action=AgentPlanAction.FALLBACK,
            reason=f"unsupported intent: {intent}",
            metadata={"intent": intent},
        )

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
        tool_input=_build_tool_input(intent, state.task_draft),
        reason=f"intent={intent} is ready and maps to tool={tool_name}",
        metadata={
            "intent": intent,
            "side_effect": tool_spec.side_effect,
            "risk_level": tool_spec.risk_level,
        },
    )


def _resolve_missing_fields(state: AgentState) -> list[str]:
    explicit_missing_fields = [field for field in state.missing_fields if field]
    if explicit_missing_fields:
        return explicit_missing_fields

    intent = _normalize_intent(state.current_intent)
    required_fields = INTENT_REQUIRED_FIELDS.get(intent or "", [])
    return [field for field in required_fields if _is_missing(state.task_draft.get(field))]


def _build_tool_input(intent: str, task_draft: dict[str, object]) -> dict[str, Any]:
    required_fields = INTENT_REQUIRED_FIELDS.get(intent, [])
    optional_fields = _optional_fields_for_intent(intent)
    allowed_fields = set(required_fields + optional_fields)
    if not allowed_fields:
        return dict(task_draft)
    return {field: task_draft[field] for field in allowed_fields if field in task_draft}


def _optional_fields_for_intent(intent: str) -> list[str]:
    if intent == "evaluate":
        return [
            "purpose",
            "normalized_date",
            "normalized_start_time",
            "normalized_end_time",
            "spans_next_day",
            "start_datetime",
            "end_datetime",
        ]
    if intent == "recommend":
        return ["purpose", "scan_hours", "min_window_hours"]
    if intent == "compare":
        return ["purpose", "top_k", "comparison_mode"]
    if intent in {"knowledge", "rag", "advice", "explain"}:
        return [
            "overall_decision",
            "risk_reasons",
            "warning_types",
            "warning_levels",
            "region",
            "province",
            "city",
            "top_k",
        ]
    return []


def _normalize_intent(intent: str | None) -> str | None:
    if intent is None:
        return None
    normalized = intent.strip().lower()
    return normalized or None


def _is_missing(value: object) -> bool:
    return value in (None, "", [])
