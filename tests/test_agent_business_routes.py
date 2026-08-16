from app.agent import (
    AgentRouteKind,
    build_route_tool_input,
    get_business_route,
    list_business_routes,
    normalize_business_intent,
    resolve_route_missing_fields,
)


def test_business_routes_cover_primary_agent_intents():
    routes = {route.intent: route for route in list_business_routes()}

    assert routes["evaluate"].primary_tool == "evaluate_flight_risk"
    assert routes["recommend"].primary_tool == "recommend_flight_windows"
    assert routes["compare"].primary_tool == "compare_flight_locations"
    assert routes["explain"].primary_tool == "explain_risk_rules"
    assert routes["explain"].route_kind == AgentRouteKind.EXPLANATION_QUERY
    assert routes["knowledge"].route_kind == AgentRouteKind.KNOWLEDGE_QUERY
    assert routes["history"].route_kind == AgentRouteKind.HISTORY_QUERY
    assert routes["knowledge"].primary_tool == "query_knowledge_snippets"
    assert routes["create_task"].primary_tool == "create_mission_task"
    assert routes["evaluate_task"].primary_tool == "evaluate_mission_task"
    assert routes["recommend_task"].primary_tool == "recommend_mission_task_windows"
    assert routes["select_task_window"].primary_tool == "select_mission_task_window"
    assert routes["preflight_check_task"].primary_tool == "preflight_check_mission_task"
    assert routes["create_task"].route_kind == AgentRouteKind.MISSION_TASK


def test_business_route_aliases_map_to_canonical_intents():
    assert normalize_business_intent("rag") == "knowledge"
    assert normalize_business_intent("advice") == "knowledge"
    assert normalize_business_intent("query_history") == "history"
    assert get_business_route("rag").primary_tool == "query_knowledge_snippets"


def test_business_route_builds_tool_input_from_allowed_fields_only():
    route = get_business_route("evaluate")

    tool_input = build_route_tool_input(
        route,
        {
            "location": "深圳",
            "date": "2026-08-02",
            "start_time": "14:00",
            "end_time": "17:00",
            "task_type": "inspection",
            "purpose": "巡检",
            "unused": "ignored",
        },
    )

    assert tool_input == {
        "location": "深圳",
        "date": "2026-08-02",
        "start_time": "14:00",
        "end_time": "17:00",
        "task_type": "inspection",
        "purpose": "巡检",
    }


def test_business_route_resolves_missing_fields():
    route = get_business_route("compare")

    missing_fields = resolve_route_missing_fields(
        route,
        {
            "locations": ["深圳", "广州"],
            "date": "2026-08-02",
            "task_type": "inspection",
        },
    )

    assert missing_fields == ["start_time", "end_time"]


def test_task_business_route_builds_task_tool_input_only():
    route = get_business_route("select_task_window")

    tool_input = build_route_tool_input(
        route,
        {
            "task_id": "task-1",
            "task_title": "深圳湾巡检",
            "window_rank": 1,
            "location": "ignored",
        },
    )

    assert tool_input == {
        "task_id": "task-1",
        "task_title": "深圳湾巡检",
        "window_rank": 1,
    }
