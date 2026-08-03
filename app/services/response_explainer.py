import json
from dataclasses import dataclass

from app.agent.guardrail import (
    GuardrailResult,
    check_output_text_guardrail,
    check_response_explanation_input_guardrail,
    guardrail_metadata,
)
from app.schemas.composed_response import UnifiedBusinessResponse
from app.services.llm_client import generate_text
from app.services.risk_output_templates import OFFICIAL_BOUNDARY_NOTE, render_business_response_template


@dataclass(frozen=True)
class ExplanationResult:
    text: str
    source: str
    llm_used: bool
    guardrail_results: list[GuardrailResult]


EXPLAINER_SYSTEM_PROMPT = """你是无人机低空任务决策系统的结果解释器。
只能基于输入的结构化结果解释，不要新增天气事实，不要推翻规则引擎结论。
输出简洁中文，包含结论、主要风险、建议。"""
CONSERVATIVE_BOUNDARY_NOTE = f"说明：{OFFICIAL_BOUNDARY_NOTE}"


def explain_business_response(response: UnifiedBusinessResponse) -> ExplanationResult:
    pre_llm_guardrail = check_response_explanation_input_guardrail(response)
    if not pre_llm_guardrail.allowed:
        return ExplanationResult(
            text=_with_conservative_boundary_note(_explain_with_template(response)),
            source="template",
            llm_used=False,
            guardrail_results=[pre_llm_guardrail],
        )

    llm_text = _explain_with_llm(response)
    if llm_text:
        post_llm_guardrail = check_output_text_guardrail(
            llm_text,
            metadata={"stage": "post_llm", "scene": response.scene},
        )
        if post_llm_guardrail.allowed:
            return ExplanationResult(
                text=llm_text,
                source="llm",
                llm_used=True,
                guardrail_results=[pre_llm_guardrail, post_llm_guardrail],
            )
        return ExplanationResult(
            text=_with_conservative_boundary_note(_explain_with_template(response)),
            source="template",
            llm_used=False,
            guardrail_results=[pre_llm_guardrail, post_llm_guardrail],
        )

    return ExplanationResult(
        text=_explain_with_template(response),
        source="template",
        llm_used=False,
        guardrail_results=[pre_llm_guardrail],
    )


def _explain_with_llm(response: UnifiedBusinessResponse) -> str | None:
    payload = response.model_dump(mode="json")
    user_prompt = json.dumps(payload, ensure_ascii=False)
    return generate_text(
        system_prompt=EXPLAINER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.2,
        max_tokens=600,
    )


def _explain_with_template(response: UnifiedBusinessResponse) -> str:
    return render_business_response_template(response)


def build_explanation_guardrail_metadata(result: ExplanationResult) -> list[dict[str, object]]:
    return [guardrail_metadata(item) for item in result.guardrail_results]


def _with_conservative_boundary_note(text: str) -> str:
    if CONSERVATIVE_BOUNDARY_NOTE in text:
        return text
    return f"{text}{CONSERVATIVE_BOUNDARY_NOTE}"
