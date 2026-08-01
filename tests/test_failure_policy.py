from app.agent import (
    ToolFailureType,
    ToolRecoveryAction,
    ToolResult,
    classify_tool_failure,
    failure_policy_metadata,
)


def test_classify_invalid_input_as_clarification():
    policy = classify_tool_failure(
        ToolResult(success=False, tool_name="evaluate_flight_risk", error_code="INVALID_TOOL_INPUT")
    )

    assert policy.failure_type == ToolFailureType.INVALID_INPUT
    assert policy.recovery_action == ToolRecoveryAction.ASK_CLARIFICATION
    assert policy.retryable is False


def test_classify_permission_error_as_deny():
    policy = classify_tool_failure(
        ToolResult(success=False, tool_name="admin_tool", error_code="ADMIN_CONTEXT_REQUIRED")
    )

    assert policy.failure_type == ToolFailureType.PERMISSION_DENIED
    assert policy.recovery_action == ToolRecoveryAction.DENY


def test_classify_external_dependency_as_retryable():
    policy = classify_tool_failure(
        ToolResult(success=False, tool_name="fetch_weather_context", error_code="WeatherRequestError")
    )

    assert policy.failure_type == ToolFailureType.EXTERNAL_DEPENDENCY_FAILED
    assert policy.recovery_action == ToolRecoveryAction.RETRY
    assert policy.retryable is True


def test_classify_unknown_error_as_legacy_fallback():
    policy = classify_tool_failure(
        ToolResult(success=False, tool_name="unknown", error_code="UnexpectedError")
    )

    assert policy.failure_type == ToolFailureType.UNKNOWN
    assert policy.recovery_action == ToolRecoveryAction.FALLBACK_LEGACY
    assert policy.retryable is False


def test_failure_policy_metadata_returns_trace_fields():
    policy = classify_tool_failure(
        ToolResult(success=False, tool_name="history", error_code="TOOL_NOT_FOUND")
    )

    assert failure_policy_metadata(policy) == {
        "failure_type": "not_found",
        "recovery_action": "direct_response",
        "retryable": False,
        "user_message": "未找到匹配结果，请调整查询条件。",
    }
