from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AgentRouteKind(StrEnum):
    BUSINESS_COMPUTE = "business_compute"
    KNOWLEDGE_QUERY = "knowledge_query"
    HISTORY_QUERY = "history_query"
    EXPLANATION_QUERY = "explanation_query"
    MISSION_TASK = "mission_task"


class AgentBusinessRoute(BaseModel):
    intent: str
    route_kind: AgentRouteKind
    target_endpoint: str
    primary_tool: str
    required_fields: list[str] = Field(default_factory=list)
    optional_fields: list[str] = Field(default_factory=list)
    description: str


BUSINESS_ROUTES: dict[str, AgentBusinessRoute] = {
    "evaluate": AgentBusinessRoute(
        intent="evaluate",
        route_kind=AgentRouteKind.BUSINESS_COMPUTE,
        target_endpoint="/cruise/evaluate",
        primary_tool="evaluate_flight_risk",
        required_fields=["location", "date", "start_time", "end_time", "task_type"],
        optional_fields=[
            "purpose",
            "normalized_date",
            "normalized_start_time",
            "normalized_end_time",
            "spans_next_day",
            "start_datetime",
            "end_datetime",
        ],
        description="单地点、指定时间段无人机低空飞行风险评估。",
    ),
    "recommend": AgentBusinessRoute(
        intent="recommend",
        route_kind=AgentRouteKind.BUSINESS_COMPUTE,
        target_endpoint="/cruise/recommend",
        primary_tool="recommend_flight_windows",
        required_fields=["location", "date", "task_type"],
        optional_fields=["purpose", "scan_hours", "min_window_hours"],
        description="为指定地点和任务类型推荐未来可执行飞行窗口。",
    ),
    "compare": AgentBusinessRoute(
        intent="compare",
        route_kind=AgentRouteKind.BUSINESS_COMPUTE,
        target_endpoint="/cruise/compare",
        primary_tool="compare_flight_locations",
        required_fields=["locations", "date", "start_time", "end_time", "task_type"],
        optional_fields=["purpose", "top_k", "comparison_mode"],
        description="对多个候选地点进行风险评估和优先级比选。",
    ),
    "knowledge": AgentBusinessRoute(
        intent="knowledge",
        route_kind=AgentRouteKind.KNOWLEDGE_QUERY,
        target_endpoint="/knowledge/advice/retrieve",
        primary_tool="query_knowledge_snippets",
        required_fields=["task_type"],
        optional_fields=[
            "query",
            "overall_decision",
            "risk_reasons",
            "risk_tags",
            "warning_types",
            "warning_levels",
            "region",
            "province",
            "city",
            "top_k",
        ],
        description="查询知识库中的风险建议、SOP、地区政策提示和 FAQ。",
    ),
    "explain": AgentBusinessRoute(
        intent="explain",
        route_kind=AgentRouteKind.EXPLANATION_QUERY,
        target_endpoint="/agent/rules/explain",
        primary_tool="explain_risk_rules",
        required_fields=[],
        optional_fields=["query", "task_type", "overall_decision", "risk_reasons", "warning_types", "warning_levels"],
        description="解释风险判定规则来源、任务阈值和预警修正逻辑。",
    ),
    "history": AgentBusinessRoute(
        intent="history",
        route_kind=AgentRouteKind.HISTORY_QUERY,
        target_endpoint="/agent/conversations",
        primary_tool="query_user_history",
        required_fields=[],
        optional_fields=["mode", "conversation_id", "keyword", "session_id", "intent", "parser_source", "page", "page_size"],
        description="查询当前登录用户自己的历史会话和任务记录。",
    ),
}

INTENT_ALIASES: dict[str, str] = {
    "advice": "knowledge",
    "rag": "knowledge",
    "query_history": "history",
}

BUSINESS_ROUTES.update(
    {
        "create_task": AgentBusinessRoute(
            intent="create_task",
            route_kind=AgentRouteKind.MISSION_TASK,
            target_endpoint="/tasks",
            primary_tool="create_mission_task",
            required_fields=["task_title", "location", "date", "start_time", "end_time", "task_type"],
            optional_fields=["purpose", "candidate_locations", "profile_context", "metadata"],
            description="Create a mission task owned by the current user.",
        ),
        "evaluate_task": AgentBusinessRoute(
            intent="evaluate_task",
            route_kind=AgentRouteKind.MISSION_TASK,
            target_endpoint="/tasks/{task_id}/evaluate",
            primary_tool="evaluate_mission_task",
            required_fields=["task_id"],
            optional_fields=["task_title", "purpose"],
            description="Evaluate an existing mission task through the task service.",
        ),
        "recommend_task": AgentBusinessRoute(
            intent="recommend_task",
            route_kind=AgentRouteKind.MISSION_TASK,
            target_endpoint="/tasks/{task_id}/recommend",
            primary_tool="recommend_mission_task_windows",
            required_fields=["task_id"],
            optional_fields=["task_title", "purpose", "scan_hours", "min_window_hours"],
            description="Recommend execution windows for an existing mission task.",
        ),
        "select_task_window": AgentBusinessRoute(
            intent="select_task_window",
            route_kind=AgentRouteKind.MISSION_TASK,
            target_endpoint="/tasks/{task_id}/select-window",
            primary_tool="select_mission_task_window",
            required_fields=["task_id", "window_rank"],
            optional_fields=["task_title", "purpose"],
            description="Select a recommended execution window for an existing mission task.",
        ),
        "preflight_check_task": AgentBusinessRoute(
            intent="preflight_check_task",
            route_kind=AgentRouteKind.MISSION_TASK,
            target_endpoint="/tasks/{task_id}/preflight-check",
            primary_tool="preflight_check_mission_task",
            required_fields=["task_id"],
            optional_fields=["task_title", "purpose"],
            description="Run an execution-time weather and rule recheck for an existing mission task.",
        ),
    }
)


def normalize_business_intent(intent: str | None) -> str | None:
    if intent is None:
        return None
    normalized = intent.strip().lower()
    if not normalized:
        return None
    return INTENT_ALIASES.get(normalized, normalized)


def get_business_route(intent: str | None) -> AgentBusinessRoute | None:
    normalized = normalize_business_intent(intent)
    if normalized is None:
        return None
    return BUSINESS_ROUTES.get(normalized)


def build_route_tool_input(route: AgentBusinessRoute, task_draft: dict[str, object]) -> dict[str, Any]:
    allowed_fields = set(route.required_fields + route.optional_fields)
    if not allowed_fields:
        return dict(task_draft)
    return {field: task_draft[field] for field in allowed_fields if field in task_draft}


def resolve_route_missing_fields(route: AgentBusinessRoute, task_draft: dict[str, object]) -> list[str]:
    return [field for field in route.required_fields if _is_missing(task_draft.get(field))]


def list_business_routes() -> list[AgentBusinessRoute]:
    return list(BUSINESS_ROUTES.values())


def _is_missing(value: object) -> bool:
    return value in (None, "", [])
