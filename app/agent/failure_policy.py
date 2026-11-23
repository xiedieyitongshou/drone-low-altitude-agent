from enum import StrEnum

from pydantic import BaseModel

from app.agent.tools import ToolResult
from app.services.weather.exceptions import WEATHER_DATA_ERROR_CODES


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

    if tool_result.error_code in WEATHER_DATA_ERROR_CODES:
        return ToolFailurePolicy(
            failure_type=ToolFailureType.EXTERNAL_DEPENDENCY_FAILED,
            recovery_action=ToolRecoveryAction.FAIL_FAST,
            retryable=bool(tool_result.metadata.get("retryable")),
            user_message=tool_result.message or "天气数据不足，本次无法完成评估。",
        )
    if tool_result.error_code in {"WeatherRequestError", "WeatherResponseError", "WeatherAuthenticationError"}:
        configuration_error = tool_result.error_code == "WeatherAuthenticationError"
        return ToolFailurePolicy(
            failure_type=ToolFailureType.EXTERNAL_DEPENDENCY_FAILED,
            recovery_action=ToolRecoveryAction.FAIL_FAST,
            retryable=not configuration_error,
            user_message=("天气服务配置异常，本次无法完成评估，请联系管理员处理。" if configuration_error else
                          "天气服务或返回数据暂时不可用，本次评估未完成，请稍后重试。"),
        )
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
            recovery_action=ToolRecoveryAction.DENY,
            user_message="当前请求缺少登录信息，请登录后再试。",
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
            recovery_action=ToolRecoveryAction.FAIL_FAST,
            user_message="外部依赖暂时不可用，请稍后重试。",
        )
    if failure_type == ToolFailureType.TIMEOUT:
        return ToolFailurePolicy(
            failure_type=failure_type,
            recovery_action=ToolRecoveryAction.FAIL_FAST,
            user_message="工具调用超时，请稍后重试。",
        )
    if failure_type == ToolFailureType.INTERNAL_ERROR:
        return ToolFailurePolicy(
            failure_type=failure_type,
            recovery_action=ToolRecoveryAction.FAIL_FAST,
            user_message="工具执行出现内部错误。",
        )

    return ToolFailurePolicy(
        failure_type=ToolFailureType.UNKNOWN,
        recovery_action=ToolRecoveryAction.FAIL_FAST,
        user_message="工具执行失败。",
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
