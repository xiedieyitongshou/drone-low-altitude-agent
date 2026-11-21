from dataclasses import dataclass, field
from typing import Any

from app.agent.business_routes import AgentRouteKind, get_business_route
from app.services.profile_memory import ProfileMemory
from app.services.run_observability import timed_stage


PENDING_TASK_KEY = "pending_task"
COMPUTE_PROFILE_FIELDS = {"task_type"}
MISSION_TASK_PROFILE_FIELDS = {"task_type", "start_time", "end_time"}
QUERY_PROFILE_FIELDS = {"location", "city", "task_type"}
DEFAULT_FIELDS_BY_INTENT: dict[str, dict[str, object]] = {
    "create_task": {"task_type": "cruise"},
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
            pending_fields = _dict_value(pending_task.get("parsed"))
            if pending_task.get("intent") != "knowledge":
                pending_fields = _session_fields(pending_fields, pending_task.get("intent"))
            merged.update(pending_fields)
            if pending_task.get("intent"):
                merged["intent"] = pending_task["intent"]
                merged["pending_task_intent"] = pending_task["intent"]
        merged.update(_session_fields(session_context, session_context.get("intent")))
    return {key: value for key, value in merged.items() if value not in (None, "", [])} or None


@timed_stage("context_merge")
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
        for field_name, value in _profile_context_for_intent(profile, route_kind=route.route_kind if route else None).items():
            _set_if_present(merged, field_sources, field_name, value, "profile", overwrite=True)

    if session_context:
        pending_task = _pending_task(session_context)
        if pending_task and (intent != "create_task" or pending_task.get("intent") == intent):
            pending_fields = _dict_value(pending_task.get("parsed"))
            if pending_task.get("intent") != "knowledge" or intent != "knowledge":
                pending_fields = _session_fields(pending_fields, pending_task.get("intent"))
            for field_name, value in pending_fields.items():
                _set_if_present(merged, field_sources, field_name, value, "session", overwrite=True)
        if intent != "create_task":
            for field_name, value in _session_fields(session_context, session_context.get("intent")).items():
                _set_if_present(merged, field_sources, field_name, value, "session", overwrite=True)
        if intent == "knowledge":
            _set_if_present(merged, field_sources, "city", session_context.get("city"), "session", overwrite=True)

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
    required_fields = list(explicit_missing_fields or route.required_fields)
    if intent == "knowledge":
        required_fields.extend(field for field in parsed.get("required_context_fields", []) if field in {"city", "as_of"})
    return [field_name for field_name in required_fields if parsed.get(field_name) in (None, "", [])]


def _profile_context_for_intent(
    profile: ProfileMemory,
    *,
    route_kind: AgentRouteKind | None,
) -> dict[str, object]:
    raw_context = profile.to_context()
    if route_kind == AgentRouteKind.MISSION_TASK:
        return {field_name: value for field_name, value in raw_context.items() if field_name in MISSION_TASK_PROFILE_FIELDS}
    if route_kind == AgentRouteKind.KNOWLEDGE_QUERY:
        return {"city": raw_context.get("location"), "task_type": raw_context.get("task_type")}
    if route_kind in {AgentRouteKind.HISTORY_QUERY, AgentRouteKind.EXPLANATION_QUERY}:
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


def _session_fields(values: dict[str, object], source_intent: object) -> dict[str, object]:
    excluded = {
        PENDING_TASK_KEY, "city", "flight_location", "flight_locations", "as_of", "required_context_fields",
        "constraint_sources", "warning_types", "warning_levels", "overall_decision", "risk_tags", "risk_reasons",
    }
    if source_intent in ("knowledge", "history", "explain"):
        excluded.update({"location", "locations"})
    fields = {key: value for key, value in values.items() if key not in excluded}
    if source_intent == "knowledge":
        # Older knowledge sessions stored the Profile default as location.
        fields.update(location=values.get("flight_location"), locations=values.get("flight_locations"))
    return fields


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
    if value in (None, "") or (value == [] and field_name not in {"warning_types", "warning_levels"}):
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
