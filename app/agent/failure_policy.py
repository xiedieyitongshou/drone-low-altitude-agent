from enum import StrEnum

from pydantic import BaseModel

from app.agent.tools import ToolResult


class ToolFailureType(StrEnum):
    INVALID_INPUT = "invalid_input"
    AUTH_REQUIRED = "auth_required"
    PERMISSION_DENIED = "permission_denied"
    NOT_FOUND = "not_found"
    EXTERNAL_DEPENDENCY_FAILED = "external_dependency_failed"
    TIMEOUT = "timeout"
    INTERNAL_ERROR = "internal_error"
    UNKNOWN = "unknown"


class ToolRecoveryAction(StrEnum):
    ASK_CLARIFICATION = "ask_clarification"
    FALLBACK_LEGACY = "fallback_legacy"
    DENY = "deny"
    DIRECT_RESPONSE = "direct_response"
    RETRY = "retry"
    FAIL_FAST = "fail_fast"


class ToolFailurePolicy(BaseModel):
    failure_type: ToolFailureType
    recovery_action: ToolRecoveryAction
    retryable: bool = False
    user_message: str


ERROR_CODE_FAILURE_TYPES: dict[str, ToolFailureType] = {
    "INVALID_TOOL_INPUT": ToolFailureType.INVALID_INPUT,
    "AUTH_CONTEXT_REQUIRED": ToolFailureType.AUTH_REQUIRED,
    "ADMIN_CONTEXT_REQUIRED": ToolFailureType.PERMISSION_DENIED,
    "TOOL_PERMISSION_DENIED": ToolFailureType.PERMISSION_DENIED,
    "TOOL_USER_SCOPE_VIOLATION": ToolFailureType.PERMISSION_DENIED,
    "TOOL_NOT_FOUND": ToolFailureType.NOT_FOUND,
    "TimeoutError": ToolFailureType.TIMEOUT,
    "TimeoutException": ToolFailureType.TIMEOUT,
    "ConnectionError": ToolFailureType.EXTERNAL_DEPENDENCY_FAILED,
    "HTTPError": ToolFailureType.EXTERNAL_DEPENDENCY_FAILED,
    "KeyError": ToolFailureType.NOT_FOUND,
    "WeatherAuthenticationError": ToolFailureType.EXTERNAL_DEPENDENCY_FAILED,
    "WeatherRequestError": ToolFailureType.EXTERNAL_DEPENDENCY_FAILED,
    "WeatherResponseError": ToolFailureType.EXTERNAL_DEPENDENCY_FAILED,
    "NaturalLanguageParseError": ToolFailureType.INVALID_INPUT,
    "RuntimeError": ToolFailureType.INTERNAL_ERROR,
    "ValueError": ToolFailureType.INVALID_INPUT,
    "MissionTaskPermissionError": ToolFailureType.PERMISSION_DENIED,
    "MissionTaskNotFoundError": ToolFailureType.NOT_FOUND,
    "MissionTaskLockedError": ToolFailureType.PERMISSION_DENIED,
    "MissionTaskMissingFieldsError": ToolFailureType.INVALID_INPUT,
    "MissionTaskWindowSelectionError": ToolFailureType.INVALID_INPUT,
}


def classify_tool_failure(tool_result: ToolResult) -> ToolFailurePolicy | None:
    if tool_result.success:
        return None

    failure_type = ERROR_CODE_FAILURE_TYPES.get(tool_result.error_code or "", ToolFailureType.UNKNOWN)
    if failure_type == ToolFailureType.INVALID_INPUT:
        return ToolFailurePolicy(
            failure_type=failure_type,
            recovery_action=ToolRecoveryAction.ASK_CLARIFICATION,
            retryable=False,
            user_message="工具输入参数不完整或格式不正确，需要补充关键信息后重试。",
        )
    if failure_type == ToolFailureType.AUTH_REQUIRED:
        return ToolFailurePolicy(
            failure_type=failure_type,
            recovery_action=ToolRecoveryAction.FALLBACK_LEGACY,
            retryable=False,
            user_message="缺少登录上下文，已尝试使用兼容链路处理。",
        )
    if failure_type == ToolFailureType.PERMISSION_DENIED:
        return ToolFailurePolicy(
            failure_type=failure_type,
            recovery_action=ToolRecoveryAction.DENY,
            retryable=False,
            user_message="当前用户没有权限执行该工具。",
        )
    if failure_type == ToolFailureType.NOT_FOUND:
        return ToolFailurePolicy(
            failure_type=failure_type,
            recovery_action=ToolRecoveryAction.DIRECT_RESPONSE,
            retryable=False,
            user_message="未找到匹配结果，请调整查询条件。",
        )
    if failure_type == ToolFailureType.EXTERNAL_DEPENDENCY_FAILED:
        return ToolFailurePolicy(
            failure_type=failure_type,
            recovery_action=ToolRecoveryAction.RETRY,
            retryable=True,
            user_message="外部依赖暂时不可用，可重试一次；仍失败时进入兼容兜底。",
        )
    if failure_type == ToolFailureType.TIMEOUT:
        return ToolFailurePolicy(
            failure_type=failure_type,
            recovery_action=ToolRecoveryAction.RETRY,
            retryable=True,
            user_message="工具调用超时，可重试一次；仍失败时进入兼容兜底。",
        )
    if failure_type == ToolFailureType.INTERNAL_ERROR:
        return ToolFailurePolicy(
            failure_type=failure_type,
            recovery_action=ToolRecoveryAction.FALLBACK_LEGACY,
            retryable=False,
            user_message="工具执行出现内部错误，已尝试使用兼容链路处理。",
        )

    return ToolFailurePolicy(
        failure_type=ToolFailureType.UNKNOWN,
        recovery_action=ToolRecoveryAction.FALLBACK_LEGACY,
        retryable=False,
        user_message="工具执行失败，已尝试使用兼容链路处理。",
    )


def failure_policy_metadata(policy: ToolFailurePolicy | None) -> dict[str, object]:
    if policy is None:
        return {}
    return {
        "failure_type": policy.failure_type.value,
        "recovery_action": policy.recovery_action.value,
        "retryable": policy.retryable,
        "user_message": policy.user_message,
    }
