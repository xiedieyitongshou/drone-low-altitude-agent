from app.agent import (
    build_agent_parser_context,
    build_pending_task_context,
    merge_agent_context,
    resolve_invalidated_tools,
)
from app.services.profile_memory import ProfileMemory


def test_parser_context_uses_session_pending_and_profile_task_type_only():
    profile = ProfileMemory(
        user_id="user-1",
        default_location="广州",
        default_task_type="inspection",
        default_start_time="14:00",
        default_end_time="17:00",
    )
    session_context = build_pending_task_context(
        intent="evaluate",
        parsed={"date": "2026-08-03", "start_time": "13:00", "end_time": "18:00"},
        missing_fields=["location"],
        query="明天下午能飞吗",
    )

    context = build_agent_parser_context(session_context=session_context, profile=profile)

    assert context["intent"] == "evaluate"
    assert context["date"] == "2026-08-03"
    assert context["task_type"] == "inspection"
    assert "location" not in context


def test_compute_merge_uses_session_but_not_profile_location():
    profile = ProfileMemory(user_id="user-1", default_location="广州", default_task_type="inspection")

    result = merge_agent_context(
        intent="evaluate",
        parsed={"location": "深圳"},
        session_context={"date": "2026-08-03", "start_time": "13:00", "end_time": "18:00"},
        profile=profile,
    )

    assert result.parsed["location"] == "深圳"
    assert result.parsed["date"] == "2026-08-03"
    assert result.parsed["task_type"] == "inspection"
    assert result.field_sources["location"] == "user_input"
    assert result.field_sources["date"] == "session"
    assert result.field_sources["task_type"] == "profile"
    assert result.missing_fields == []


def test_compute_merge_does_not_fill_safety_location_from_profile():
    profile = ProfileMemory(user_id="user-1", default_location="广州", default_task_type="inspection")

    result = merge_agent_context(
        intent="evaluate",
        parsed={"date": "2026-08-03", "start_time": "13:00", "end_time": "18:00"},
        session_context=None,
        profile=profile,
    )

    assert "location" not in result.parsed
    assert result.missing_fields == ["location"]


def test_query_merge_can_use_profile_location_and_defaults():
    profile = ProfileMemory(user_id="user-1", default_location="深圳", default_task_type="inspection")

    result = merge_agent_context(
        intent="knowledge",
        parsed={"query": "政策有什么要注意"},
        session_context=None,
        profile=profile,
    )

    assert result.parsed["city"] == "深圳"
    assert result.parsed["task_type"] == "inspection"
    assert result.parsed["top_k"] == 3
    assert result.field_sources["city"] == "profile"
    assert result.field_sources["top_k"] == "default"


def test_user_input_override_marks_modified_fields_and_invalidated_tools():
    result = merge_agent_context(
        intent="evaluate",
        parsed={"location": "广州"},
        session_context={
            "intent": "evaluate",
            "location": "深圳",
            "date": "2026-08-03",
            "start_time": "13:00",
            "end_time": "18:00",
            "task_type": "inspection",
        },
        profile=None,
    )

    assert result.parsed["location"] == "广州"
    assert result.field_sources["location"] == "user_input"
    assert result.modified_fields == ["location"]
    assert result.invalidated_tools == ["evaluate_flight_risk", "query_knowledge_snippets"]


def test_supplementing_missing_field_is_not_treated_as_modification():
    result = merge_agent_context(
        intent="evaluate",
        parsed={"location": "深圳"},
        session_context={
            "intent": "evaluate",
            "date": "2026-08-03",
            "start_time": "13:00",
            "end_time": "18:00",
            "task_type": "inspection",
        },
        profile=None,
    )

    assert result.modified_fields == []
    assert result.invalidated_tools == []


def test_resolve_invalidated_tools_for_task_type_change():
    assert resolve_invalidated_tools(intent="recommend", modified_fields=["task_type"]) == [
        "recommend_flight_windows",
        "query_knowledge_snippets",
    ]
