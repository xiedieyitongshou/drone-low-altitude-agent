from app.agent import (
    ToolExecutionContext,
    ToolNotFoundError,
    ToolRegistry,
    ToolRegistrationError,
    ToolSpec,
    default_tool_registry,
)


def test_tool_registry_registers_and_lists_specs():
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="echo",
            description="Return input payload.",
            side_effect="read_only",
            risk_level="low",
            requires_auth=False,
        ),
        lambda payload, context: payload,
    )

    assert registry.get("echo").spec.name == "echo"
    assert [item.name for item in registry.list_specs()] == ["echo"]


def test_tool_registry_rejects_duplicate_registration():
    registry = ToolRegistry()
    spec = ToolSpec(
        name="echo",
        description="Return input payload.",
        side_effect="read_only",
        risk_level="low",
        requires_auth=False,
    )
    registry.register(spec, lambda payload, context: payload)

    try:
        registry.register(spec, lambda payload, context: payload)
    except ToolRegistrationError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("duplicate tool registration should fail")


def test_tool_registry_missing_tool_returns_structured_error():
    result = ToolRegistry().call("missing_tool", {})

    assert result.success is False
    assert result.tool_name == "missing_tool"
    assert result.error_code == "TOOL_NOT_FOUND"


def test_tool_registry_auth_context_required():
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="secure_tool",
            description="Requires authenticated user.",
            side_effect="read_only",
            risk_level="low",
        ),
        lambda payload, context: payload,
    )

    result = registry.call("secure_tool", {})

    assert result.success is False
    assert result.error_code == "AUTH_CONTEXT_REQUIRED"


def test_tool_registry_wraps_handler_exception():
    registry = ToolRegistry()

    def broken_handler(payload, context):
        raise RuntimeError("boom")

    registry.register(
        ToolSpec(
            name="broken_tool",
            description="Raise runtime error.",
            side_effect="compute_only",
            risk_level="medium",
            requires_auth=False,
        ),
        broken_handler,
    )

    result = registry.call("broken_tool", {})

    assert result.success is False
    assert result.error_code == "RuntimeError"
    assert result.message == "boom"


def test_default_registry_contains_day72_core_tools():
    names = {item.name for item in default_tool_registry.list_specs()}

    assert {
        "evaluate_flight_risk",
        "recommend_flight_windows",
        "compare_flight_locations",
        "retrieve_rag_advice",
        "query_user_history",
    }.issubset(names)


def test_retrieve_rag_advice_tool_applies_context_filters():
    result = default_tool_registry.call(
        "retrieve_rag_advice",
        {
            "task_type": "inspection",
            "risk_reasons": ["强风"],
            "warning_types": [],
            "warning_levels": [],
            "province": "广东",
            "city": "深圳",
            "top_k": 3,
        },
        context=ToolExecutionContext(user_id="user-1", tenant_id="public", role="user"),
    )

    assert result.success is True
    assert result.tool_name == "retrieve_rag_advice"
    assert "snippets" in result.data
    assert result.metadata["side_effect"] == "read_only"
