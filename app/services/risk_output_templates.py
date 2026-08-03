from typing import Literal

from app.schemas.composed_response import UnifiedBusinessResponse


RiskOutputTemplateKind = Literal[
    "prohibited",
    "caution",
    "suitable",
    "no_recommendation",
    "comparison",
    "history",
    "unknown",
]


OFFICIAL_BOUNDARY_NOTE = "本系统不能替代官方审批，涉及政策、管制或合规要求时应以当地主管部门最新要求为准。"
UNSAFE_OUTPUT_KEYWORDS = ("绝对安全", "一定能飞", "无需审批", "不用审批", "保证通过", "肯定合法", "绕过审批", "不用报备")


def render_business_response_template(response: UnifiedBusinessResponse) -> str:
    if response.scene == "recommend":
        return _render_recommendation_template(response)
    if response.scene == "compare":
        return _render_comparison_template(response)
    if response.scene == "history":
        return _render_history_template(response)
    return _render_evaluation_template(response)


def find_unsafe_output_keywords(text: str) -> list[str]:
    return [keyword for keyword in UNSAFE_OUTPUT_KEYWORDS if keyword in text]


def template_kind(response: UnifiedBusinessResponse) -> RiskOutputTemplateKind:
    if response.scene == "recommend" and not response.recommended_windows:
        return "no_recommendation"
    if response.scene == "compare":
        return "comparison"
    if response.scene == "history":
        return "history"

    decision = str(response.overall_decision or "")
    if "禁飞" in decision:
        return "prohibited"
    if "谨慎" in decision:
        return "caution"
    if "适飞" in decision:
        return "suitable"
    return "unknown"


def _render_evaluation_template(response: UnifiedBusinessResponse) -> str:
    kind = template_kind(response)
    if kind == "prohibited":
        conclusion = "当前结论：不建议执行本次无人机任务。"
        action = "建议动作：暂停任务，重新选择时间窗口或补充官方审批/现场确认信息。"
    elif kind == "caution":
        conclusion = "当前结论：建议谨慎执行，不应直接按低风险任务处理。"
        action = "建议动作：降低飞行高度和作业强度，执行前复核天气、预警和现场限制。"
    elif kind == "suitable" and response.allow_execute is True:
        conclusion = "当前结论：当前条件下风险较低，但仍需执行飞行前复核。"
        action = "建议动作：按既定任务计划准备，同时继续关注天气、预警和现场管制变化。"
    else:
        conclusion = "当前结论：系统无法给出明确适飞结论。"
        action = "建议动作：补充任务地点、时间、任务类型或政策依据后重新评估。"

    return _join_template_parts(
        conclusion=conclusion,
        reasons=_format_reasons(response.risk_reasons),
        boundary=_boundary_text(response),
        action=action,
    )


def _render_recommendation_template(response: UnifiedBusinessResponse) -> str:
    if not response.recommended_windows:
        return _join_template_parts(
            conclusion="当前结论：没有找到满足条件的推荐飞行窗口。",
            reasons=_format_reasons(response.risk_reasons),
            boundary=_boundary_text(response),
            action="建议动作：放宽时间范围、调整任务条件，或等待天气和预警条件改善后重试。",
        )

    top_window = response.recommended_windows[0]
    reasons = top_window.reasons or response.risk_reasons
    return _join_template_parts(
        conclusion=f"当前结论：优先推荐 {top_window.start_time} 到 {top_window.end_time} 作为候选窗口。",
        reasons=_format_reasons(reasons),
        boundary=_boundary_text(response),
        action="建议动作：将该窗口作为候选方案，执行前仍需复核实时天气、预警和现场限制。",
    )


def _render_comparison_template(response: UnifiedBusinessResponse) -> str:
    if not response.ranked_locations:
        return _join_template_parts(
            conclusion="当前结论：多地点比选没有得到可排序结果。",
            reasons=_format_reasons(response.risk_reasons),
            boundary=_boundary_text(response),
            action="建议动作：检查候选地点、任务时间和任务类型是否完整后重新比选。",
        )

    top_location = response.ranked_locations[0]
    return _join_template_parts(
        conclusion=f"当前结论：当前优先候选地点为 {top_location.location}。",
        reasons=top_location.summary_reason or _format_reasons(response.risk_reasons),
        boundary=_boundary_text(response),
        action="建议动作：将该地点作为候选方案，执行前继续复核实时天气、预警和现场管制。",
    )


def _render_history_template(response: UnifiedBusinessResponse) -> str:
    if not response.history_summary:
        return _join_template_parts(
            conclusion=f"当前结论：{response.summary}",
            reasons=_format_reasons(response.risk_reasons),
            boundary=_boundary_text(response),
            action="建议动作：如需复用历史任务，请重新确认当前天气、预警和现场条件。",
        )

    history = response.history_summary
    return _join_template_parts(
        conclusion=f"当前结论：历史任务 {history.request_id} 的结论为 {history.overall_decision}。",
        reasons=_format_reasons(response.risk_reasons),
        boundary=_boundary_text(response),
        action="建议动作：历史结果只能作为参考，重新执行前应按当前条件重新评估。",
    )


def _format_reasons(risk_reasons: list[str]) -> str:
    if not risk_reasons:
        return "主要依据：当前结构化结果中未发现明确高风险因素。"
    return "主要依据：" + "；".join(risk_reasons[:5]) + "。"


def _boundary_text(response: UnifiedBusinessResponse) -> str:
    if _requires_official_boundary(response):
        return f"边界说明：{OFFICIAL_BOUNDARY_NOTE}"
    return "边界说明：系统结论基于当前输入、天气数据和规则评估结果，执行前仍需复核实时条件。"


def _requires_official_boundary(response: UnifiedBusinessResponse) -> bool:
    text = " ".join(
        [
            response.summary,
            str(response.overall_decision or ""),
            " ".join(response.risk_reasons),
            str(response.details.get("advice") if response.details else ""),
            str(response.details.get("knowledge_snippets") if response.details else ""),
        ]
    )
    return any(term in text for term in ("政策", "审批", "许可", "禁飞", "管制", "实名", "合规"))


def _join_template_parts(*, conclusion: str, reasons: str, boundary: str, action: str) -> str:
    return "\n".join([conclusion, reasons, boundary, action])
