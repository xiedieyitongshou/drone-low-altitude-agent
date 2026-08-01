from dataclasses import dataclass, field
from typing import Any

from app.agent.business_routes import AgentRouteKind, get_business_route
from app.services.profile_memory import ProfileMemory


PENDING_TASK_KEY = "pending_task"
COMPUTE_PROFILE_FIELDS = {"task_type"}
QUERY_PROFILE_FIELDS = {"location", "city", "task_type"}
DEFAULT_FIELDS_BY_INTENT: dict[str, dict[str, object]] = {
    "history": {"mode": "list", "page": 1, "page_size": 10},
    "knowledge": {"task_type": "cruise", "top_k": 3},
    "explain": {"task_type": "cruise"},
}


@dataclass(frozen=True)
class AgentContextMergeResult:
    intent: str
    parsed: dict[str, object]
    missing_fields: list[str] = field(default_factory=list)
    field_sources: dict[str, str] = field(default_factory=dict)
    modified_fields: list[str] = field(default_factory=list)
    invalidated_tools: list[str] = field(default_factory=list)
    context_used: bool = False


def build_agent_parser_context(
    *,
    session_context: dict[str, object] | None,
    profile: ProfileMemory | None,
) -> dict[str, object] | None:
    merged: dict[str, object] = {}
    if profile and profile.default_task_type:
        merged["task_type"] = profile.default_task_type
    if session_context:
        pending_task = _pending_task(session_context)
        if pending_task:
            merged.update(_dict_value(pending_task.get("parsed")))
            if pending_task.get("intent"):
                merged["intent"] = pending_task["intent"]
        merged.update({key: value for key, value in session_context.items() if key != PENDING_TASK_KEY})
    return {key: value for key, value in merged.items() if value not in (None, "", [])} or None


def merge_agent_context(
    *,
    intent: str,
    parsed: dict[str, object],
    session_context: dict[str, object] | None,
    profile: ProfileMemory | None,
    missing_fields: list[str] | None = None,
) -> AgentContextMergeResult:
    route = get_business_route(intent)
    merged: dict[str, object] = {}
    field_sources: dict[str, str] = {}
    modified_fields: list[str] = []

    for field_name, value in _defaults_for_intent(intent).items():
        _set_if_present(merged, field_sources, field_name, value, "default", overwrite=False)

    if profile is not None:
        for field_name, value in _profile_context_for_intent(intent, profile, route_kind=route.route_kind if route else None).items():
            _set_if_present(merged, field_sources, field_name, value, "profile", overwrite=True)

    if session_context:
        pending_task = _pending_task(session_context)
        if pending_task:
            for field_name, value in _dict_value(pending_task.get("parsed")).items():
                _set_if_present(merged, field_sources, field_name, value, "session", overwrite=True)
        for field_name, value in session_context.items():
            if field_name == PENDING_TASK_KEY:
                continue
            _set_if_present(merged, field_sources, field_name, value, "session", overwrite=True)

    for field_name, value in parsed.items():
        _set_if_present(
            merged,
            field_sources,
            field_name,
            value,
            "user_input",
            overwrite=True,
            modified_fields=modified_fields,
        )

    unresolved = _resolve_missing_fields(intent=intent, parsed=merged, explicit_missing_fields=missing_fields)
    return AgentContextMergeResult(
        intent=intent,
        parsed=merged,
        missing_fields=unresolved,
        field_sources=field_sources,
        modified_fields=modified_fields,
        invalidated_tools=resolve_invalidated_tools(intent=intent, modified_fields=modified_fields),
        context_used=any(source in {"session", "profile", "default"} for source in field_sources.values()),
    )


def build_pending_task_context(
    *,
    intent: str,
    parsed: dict[str, object],
    missing_fields: list[str],
    query: str,
) -> dict[str, object]:
    return {
        PENDING_TASK_KEY: {
            "intent": intent,
            "parsed": dict(parsed),
            "missing_fields": list(missing_fields),
            "query": query,
        },
        "intent": intent,
        **{key: value for key, value in parsed.items() if value not in (None, "", [])},
    }


def resolve_invalidated_tools(*, intent: str, modified_fields: list[str]) -> list[str]:
    if not modified_fields:
        return []

    route = get_business_route(intent)
    invalidated: list[str] = []
    modified = set(modified_fields)

    if route and modified & set(route.required_fields + route.optional_fields):
        invalidated.append(route.primary_tool)

    if modified & {"location", "locations", "city", "province", "region", "task_type", "risk_reasons", "overall_decision"}:
        if "query_knowledge_snippets" not in invalidated:
            invalidated.append("query_knowledge_snippets")

    return invalidated


def _resolve_missing_fields(
    *,
    intent: str,
    parsed: dict[str, object],
    explicit_missing_fields: list[str] | None,
) -> list[str]:
    route = get_business_route(intent)
    if route is None:
        return explicit_missing_fields or []
    required_fields = explicit_missing_fields or route.required_fields
    return [field_name for field_name in required_fields if parsed.get(field_name) in (None, "", [])]


def _profile_context_for_intent(
    intent: str,
    profile: ProfileMemory,
    *,
    route_kind: AgentRouteKind | None,
) -> dict[str, object]:
    raw_context = profile.to_context()
    if route_kind in {AgentRouteKind.KNOWLEDGE_QUERY, AgentRouteKind.HISTORY_QUERY, AgentRouteKind.EXPLANATION_QUERY}:
        context = {field_name: value for field_name, value in raw_context.items() if field_name in QUERY_PROFILE_FIELDS}
        if "location" in context:
            context["city"] = context["location"]
        return context
    return {field_name: value for field_name, value in raw_context.items() if field_name in COMPUTE_PROFILE_FIELDS}


def _defaults_for_intent(intent: str) -> dict[str, object]:
    return dict(DEFAULT_FIELDS_BY_INTENT.get(intent, {}))


def _pending_task(context: dict[str, object]) -> dict[str, object] | None:
    value = context.get(PENDING_TASK_KEY)
    return value if isinstance(value, dict) else None


def _dict_value(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _set_if_present(
    target: dict[str, object],
    sources: dict[str, str],
    field_name: str,
    value: object,
    source: str,
    *,
    overwrite: bool,
    modified_fields: list[str] | None = None,
) -> None:
    if value in (None, "", []):
        return
    if (
        source == "user_input"
        and field_name in target
        and target[field_name] != value
        and sources.get(field_name) in {"session", "profile", "default"}
        and modified_fields is not None
        and field_name not in modified_fields
    ):
        modified_fields.append(field_name)
    if overwrite or field_name not in target:
        target[field_name] = value
        sources[field_name] = source
