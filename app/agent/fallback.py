from typing import Any

from app.agent.failure_policy import ToolFailurePolicy, ToolFailureType, ToolRecoveryAction
from app.agent.state import AgentState
from app.agent.tools import ToolResult


FIELD_DISPLAY_NAMES = {
    "location": "任务地点",
    "locations": "候选地点",
    "date": "任务日期",
    "start_time": "开始时间",
    "end_time": "结束时间",
    "task_type": "任务类型",
    "query": "问题内容",
}


def build_clarification_message(missing_fields: list[str]) -> str:
    if not missing_fields:
        return "还需要补充更多任务信息后才能继续。"
    field_names = [FIELD_DISPLAY_NAMES.get(field, field) for field in missing_fields]
    return f"还需要补充以下信息后才能继续：{'、'.join(field_names)}。"


def build_empty_result_message(tool_name: str | None) -> str:
    if tool_name == "retrieve_rag_advice":
        return "当前知识库没有召回匹配内容，建议补充地区、任务类型或具体风险场景后再试。"
    if tool_name == "query_user_history":
        return "没有查询到匹配的历史记录，可以调整关键词、会话或时间条件后再试。"
    if tool_name == "recommend_flight_windows":
        return "当前条件下没有找到合适的推荐窗口，可以放宽时间范围或调整任务条件后再试。"
    return "当前没有找到匹配结果，可以调整条件后再试。"


def build_tool_failure_message(
    *,
    policy: ToolFailurePolicy | None,
    tool_result: ToolResult | None = None,
    tool_name: str | None = None,
) -> str:
    if policy is None:
        return tool_result.message if tool_result and tool_result.message else "工具执行失败，系统已进入兜底处理。"
    if policy.recovery_action == ToolRecoveryAction.ASK_CLARIFICATION:
        return policy.user_message
    if policy.recovery_action == ToolRecoveryAction.DENY:
        return policy.user_message
    if policy.recovery_action == ToolRecoveryAction.DIRECT_RESPONSE:
        return build_empty_result_message(tool_name)
    if policy.failure_type in {ToolFailureType.EXTERNAL_DEPENDENCY_FAILED, ToolFailureType.TIMEOUT}:
        return policy.user_message
    return policy.user_message


def build_agent_fallback_output(
    *,
    state: AgentState,
    message: str,
    policy: ToolFailurePolicy | None = None,
    tool_name: str | None = None,
    fallback_used: bool = False,
) -> dict[str, Any]:
    return {
        "message": message,
        "trace_id": state.trace_id,
        "run_id": state.run_id,
        "status": state.status.value,
        "tool_name": tool_name,
        "fallback_used": fallback_used,
        "failure_type": policy.failure_type.value if policy else None,
        "recovery_action": policy.recovery_action.value if policy else None,
        "retryable": policy.retryable if policy else False,
        "errors": state.errors,
    }
