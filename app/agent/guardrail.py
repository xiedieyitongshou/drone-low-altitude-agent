from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.agent.state import AgentState
from app.agent.tools import ToolExecutionContext, ToolSpec


class GuardrailCheckpoint(StrEnum):
    INPUT = "input"
    TOOL = "tool"
    OUTPUT = "output"


class GuardrailAction(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"
    ASK_CLARIFICATION = "ask_clarification"
    FALLBACK = "fallback"


class GuardrailResult(BaseModel):
    checkpoint: GuardrailCheckpoint
    action: GuardrailAction = GuardrailAction.ALLOW
    allowed: bool = True
    reason: str = "allowed"
    error_code: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GuardrailExplanation(BaseModel):
    checkpoint: str
    action: str
    allowed: bool
    error_code: str | None = None
    reason: str
    user_message: str
    violation_type: str | None = None
    tool_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


DANGEROUS_INPUT_KEYWORDS = ("破解", "绕过审批", "绕过禁飞", "伪造资质", "关闭监管")
ABSOLUTE_POLICY_PHRASES = ("绝对安全", "一定能飞", "无需审批", "不用审批", "保证通过")
POLICY_SENSITIVE_TERMS = ("政策", "审批", "许可", "禁飞", "管制", "实名", "合规")
GUARDRAIL_USER_MESSAGES = {
    "INPUT_EMPTY": "请输入具体任务或问题后再继续。",
    "DANGEROUS_INPUT": "当前输入涉及绕过监管或危险操作，系统已拒绝继续执行。",
    "AUTH_CONTEXT_REQUIRED": "当前操作需要登录后才能继续。",
    "ADMIN_CONTEXT_REQUIRED": "当前工具需要管理员权限，普通用户不能调用。",
    "TOOL_PERMISSION_DENIED": "当前用户无权调用该工具。",
    "TOOL_USER_SCOPE_VIOLATION": "请求中的用户身份与当前登录用户不一致，系统已拒绝越权访问。",
    "UNSAFE_FINAL_RESPONSE": "系统检测到最终回答存在过度承诺，已降级处理。",
    "MISSING_POLICY_EVIDENCE_FOR_LLM": "当前缺少明确政策依据，系统不会使用大模型扩写该结论。",
}


def allow_guardrail(checkpoint: GuardrailCheckpoint, *, metadata: dict[str, Any] | None = None) -> GuardrailResult:
    return GuardrailResult(checkpoint=checkpoint, metadata=metadata or {})


def check_input_guardrail(state: AgentState) -> GuardrailResult:
    query = state.query.strip()
    if not query:
        return GuardrailResult(
            checkpoint=GuardrailCheckpoint.INPUT,
            action=GuardrailAction.ASK_CLARIFICATION,
            allowed=False,
            reason="用户输入为空，需要补充具体问题。",
            error_code="INPUT_EMPTY",
        )

    matched_keywords = [keyword for keyword in DANGEROUS_INPUT_KEYWORDS if keyword in query]
    if matched_keywords:
        return GuardrailResult(
            checkpoint=GuardrailCheckpoint.INPUT,
            action=GuardrailAction.BLOCK,
            allowed=False,
            reason="用户输入包含绕过监管或危险操作意图。",
            error_code="DANGEROUS_INPUT",
            metadata={"matched_keywords": matched_keywords},
        )

    return allow_guardrail(
        GuardrailCheckpoint.INPUT,
        metadata={"query_length": len(query)},
    )


def check_tool_guardrail(
    *,
    tool_spec: ToolSpec,
    tool_input: dict[str, object],
    state: AgentState,
    context: ToolExecutionContext,
) -> GuardrailResult:
    effective_user_id = context.user_id or state.user_id
    actual_role = context.role or "user"

    if tool_spec.requires_auth and not effective_user_id:
        return GuardrailResult(
            checkpoint=GuardrailCheckpoint.TOOL,
            action=GuardrailAction.FALLBACK,
            allowed=False,
            reason="工具需要登录上下文，但当前请求缺少用户身份。",
            error_code="AUTH_CONTEXT_REQUIRED",
            metadata=_tool_guardrail_metadata(
                tool_spec,
                tool_input,
                actual_role=actual_role,
                violation_type="missing_auth_context",
            ),
        )

    if tool_spec.requires_admin and context.role != "admin":
        return GuardrailResult(
            checkpoint=GuardrailCheckpoint.TOOL,
            action=GuardrailAction.BLOCK,
            allowed=False,
            reason="工具需要管理员权限，当前用户无权调用。",
            error_code="ADMIN_CONTEXT_REQUIRED",
            metadata=_tool_guardrail_metadata(
                tool_spec,
                tool_input,
                actual_role=actual_role,
                violation_type="admin_required",
            ),
        )

    if actual_role not in tool_spec.allowed_roles:
        return GuardrailResult(
            checkpoint=GuardrailCheckpoint.TOOL,
            action=GuardrailAction.BLOCK,
            allowed=False,
            reason="当前用户角色不允许调用该工具。",
            error_code="TOOL_PERMISSION_DENIED",
            metadata=_tool_guardrail_metadata(
                tool_spec,
                tool_input,
                actual_role=actual_role,
                violation_type="role_not_allowed",
            ),
        )

    payload_user_id = _extract_payload_user_id(tool_input)
    if tool_spec.user_scope == "current_user" and payload_user_id and payload_user_id != effective_user_id:
        return GuardrailResult(
            checkpoint=GuardrailCheckpoint.TOOL,
            action=GuardrailAction.BLOCK,
            allowed=False,
            reason="工具输入中的 user_id 与当前登录用户不一致，疑似越权访问。",
            error_code="TOOL_USER_SCOPE_VIOLATION",
            metadata=_tool_guardrail_metadata(
                tool_spec,
                tool_input,
                actual_role=actual_role,
                violation_type="payload_user_id_mismatch",
                payload_user_id=payload_user_id,
            ),
        )

    if tool_spec.user_scope == "admin" and actual_role != "admin":
        return GuardrailResult(
            checkpoint=GuardrailCheckpoint.TOOL,
            action=GuardrailAction.BLOCK,
            allowed=False,
            reason="该工具作用域为管理员，当前用户无权调用。",
            error_code="TOOL_PERMISSION_DENIED",
            metadata=_tool_guardrail_metadata(
                tool_spec,
                tool_input,
                actual_role=actual_role,
                violation_type="admin_scope_required",
            ),
        )

    return allow_guardrail(
        GuardrailCheckpoint.TOOL,
        metadata=_tool_guardrail_metadata(tool_spec, tool_input, actual_role=actual_role),
    )


def check_output_guardrail(
    *,
    state: AgentState,
    output: Any,
    message: str | None = None,
) -> GuardrailResult:
    output_text = _stringify_output(output, message=message)
    return check_output_text_guardrail(
        output_text,
        metadata={"intent": state.current_intent},
    )


def check_output_text_guardrail(
    text: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> GuardrailResult:
    matched_phrases = [phrase for phrase in ABSOLUTE_POLICY_PHRASES if phrase in text]
    if matched_phrases:
        return GuardrailResult(
            checkpoint=GuardrailCheckpoint.OUTPUT,
            action=GuardrailAction.FALLBACK,
            allowed=False,
            reason="最终回答包含过度确定或缺少依据的安全/审批承诺。",
            error_code="UNSAFE_FINAL_RESPONSE",
            metadata={
                **(metadata or {}),
                "matched_phrases": matched_phrases,
            },
        )

    return allow_guardrail(
        GuardrailCheckpoint.OUTPUT,
        metadata=metadata,
    )


def check_response_explanation_input_guardrail(response: Any) -> GuardrailResult:
    details = getattr(response, "details", {}) or {}
    text = _build_response_text(response)
    policy_terms = [term for term in POLICY_SENSITIVE_TERMS if term in text]
    knowledge_snippets = details.get("knowledge_snippets") if isinstance(details, dict) else None
    has_knowledge_evidence = isinstance(knowledge_snippets, list) and bool(knowledge_snippets)

    if policy_terms and not has_knowledge_evidence:
        return GuardrailResult(
            checkpoint=GuardrailCheckpoint.OUTPUT,
            action=GuardrailAction.FALLBACK,
            allowed=False,
            reason="响应涉及政策、审批或管制表述，但缺少可引用知识依据，不交给 LLM 扩写。",
            error_code="MISSING_POLICY_EVIDENCE_FOR_LLM",
            metadata={
                "stage": "pre_llm",
                "scene": getattr(response, "scene", None),
                "policy_terms": policy_terms,
                "has_knowledge_evidence": has_knowledge_evidence,
            },
        )

    return allow_guardrail(
        GuardrailCheckpoint.OUTPUT,
        metadata={
            "stage": "pre_llm",
            "scene": getattr(response, "scene", None),
            "has_knowledge_evidence": has_knowledge_evidence,
        },
    )


def guardrail_metadata(result: GuardrailResult) -> dict[str, Any]:
    explanation = build_guardrail_explanation(result)
    return {
        "guardrail_checkpoint": result.checkpoint.value,
        "guardrail_action": result.action.value,
        "guardrail_allowed": result.allowed,
        "guardrail_reason": result.reason,
        "guardrail_user_message": explanation.user_message,
        "guardrail_explanation": explanation.model_dump(mode="json"),
        **result.metadata,
    }


def build_guardrail_explanation(result: GuardrailResult) -> GuardrailExplanation:
    metadata = dict(result.metadata)
    return GuardrailExplanation(
        checkpoint=result.checkpoint.value,
        action=result.action.value,
        allowed=result.allowed,
        error_code=result.error_code,
        reason=result.reason,
        user_message=_guardrail_user_message(result),
        violation_type=_safe_optional_str(metadata.get("violation_type")),
        tool_name=_safe_optional_str(metadata.get("tool_name")),
        metadata=metadata,
    )


def extract_guardrail_explanation_from_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metadata:
        return None
    explanation = metadata.get("guardrail_explanation")
    if isinstance(explanation, dict):
        return explanation
    if "guardrail_checkpoint" not in metadata:
        return None
    return {
        "checkpoint": metadata.get("guardrail_checkpoint"),
        "action": metadata.get("guardrail_action"),
        "allowed": metadata.get("guardrail_allowed"),
        "error_code": metadata.get("error_code"),
        "reason": metadata.get("guardrail_reason"),
        "user_message": metadata.get("guardrail_user_message") or metadata.get("guardrail_reason"),
        "violation_type": metadata.get("violation_type"),
        "tool_name": metadata.get("tool_name"),
        "metadata": metadata,
    }


def _guardrail_user_message(result: GuardrailResult) -> str:
    if result.error_code and result.error_code in GUARDRAIL_USER_MESSAGES:
        return GUARDRAIL_USER_MESSAGES[result.error_code]
    if result.allowed:
        return "Guardrail 检查通过。"
    return result.reason


def _safe_optional_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _tool_guardrail_metadata(
    tool_spec: ToolSpec,
    tool_input: dict[str, object],
    *,
    actual_role: str | None = None,
    violation_type: str | None = None,
    payload_user_id: str | None = None,
) -> dict[str, Any]:
    metadata = {
        "tool_name": tool_spec.name,
        "side_effect": tool_spec.side_effect,
        "risk_level": tool_spec.risk_level,
        "requires_auth": tool_spec.requires_auth,
        "requires_admin": tool_spec.requires_admin,
        "allowed_roles": list(tool_spec.allowed_roles),
        "actual_role": actual_role,
        "user_scope": tool_spec.user_scope,
        "input_fields": sorted(tool_input.keys()),
    }
    if violation_type:
        metadata["violation_type"] = violation_type
    if payload_user_id:
        metadata["payload_user_id"] = payload_user_id
    return metadata


def _extract_payload_user_id(tool_input: dict[str, object]) -> str | None:
    value = tool_input.get("user_id")
    if value in (None, ""):
        return None
    return str(value)


def _stringify_output(output: Any, *, message: str | None = None) -> str:
    if message:
        return message
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    return str(output)


def _build_response_text(response: Any) -> str:
    parts = [
        str(getattr(response, "summary", "") or ""),
        str(getattr(response, "overall_decision", "") or ""),
        " ".join(str(item) for item in getattr(response, "risk_reasons", []) or []),
    ]
    details = getattr(response, "details", {}) or {}
    if isinstance(details, dict):
        parts.append(str(details.get("advice") or ""))
        parts.append(str(details.get("knowledge_snippets") or ""))
    return " ".join(parts)
