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


DANGEROUS_INPUT_KEYWORDS = ("破解", "绕过审批", "绕过禁飞", "伪造资质", "关闭监管")
ABSOLUTE_POLICY_PHRASES = ("绝对安全", "一定能飞", "无需审批", "不用审批", "保证通过")
POLICY_SENSITIVE_TERMS = ("政策", "审批", "许可", "禁飞", "管制", "实名", "合规")


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
    if tool_spec.requires_auth and not (context.user_id or state.user_id):
        return GuardrailResult(
            checkpoint=GuardrailCheckpoint.TOOL,
            action=GuardrailAction.FALLBACK,
            allowed=False,
            reason="工具需要登录上下文，但当前请求缺少用户身份。",
            error_code="AUTH_CONTEXT_REQUIRED",
            metadata=_tool_guardrail_metadata(tool_spec, tool_input),
        )

    if tool_spec.requires_admin and context.role != "admin":
        return GuardrailResult(
            checkpoint=GuardrailCheckpoint.TOOL,
            action=GuardrailAction.BLOCK,
            allowed=False,
            reason="工具需要管理员权限，当前用户无权调用。",
            error_code="ADMIN_CONTEXT_REQUIRED",
            metadata=_tool_guardrail_metadata(tool_spec, tool_input),
        )

    return allow_guardrail(
        GuardrailCheckpoint.TOOL,
        metadata=_tool_guardrail_metadata(tool_spec, tool_input),
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
    return {
        "guardrail_checkpoint": result.checkpoint.value,
        "guardrail_action": result.action.value,
        "guardrail_allowed": result.allowed,
        "guardrail_reason": result.reason,
        **result.metadata,
    }


def _tool_guardrail_metadata(tool_spec: ToolSpec, tool_input: dict[str, object]) -> dict[str, Any]:
    return {
        "tool_name": tool_spec.name,
        "side_effect": tool_spec.side_effect,
        "risk_level": tool_spec.risk_level,
        "requires_auth": tool_spec.requires_auth,
        "requires_admin": tool_spec.requires_admin,
        "input_fields": sorted(tool_input.keys()),
    }


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
