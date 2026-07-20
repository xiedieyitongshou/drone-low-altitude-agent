import json
from dataclasses import dataclass

from app.schemas.composed_response import UnifiedBusinessResponse
from app.services.llm_client import generate_text


@dataclass(frozen=True)
class ExplanationResult:
    text: str
    source: str
    llm_used: bool


EXPLAINER_SYSTEM_PROMPT = """你是无人机低空任务决策系统的结果解释器。
只能基于输入的结构化结果解释，不要新增天气事实，不要推翻规则引擎结论。
输出简洁中文，包含结论、主要风险、建议。"""


def explain_business_response(response: UnifiedBusinessResponse) -> ExplanationResult:
    llm_text = _explain_with_llm(response)
    if llm_text:
        return ExplanationResult(text=llm_text, source="llm", llm_used=True)

    return ExplanationResult(
        text=_explain_with_template(response),
        source="template",
        llm_used=False,
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
    if response.scene == "recommend":
        return _explain_recommendation(response)
    if response.scene == "compare":
        return _explain_comparison(response)
    if response.scene == "history":
        return _explain_history(response)
    return _explain_evaluation(response)


def _explain_evaluation(response: UnifiedBusinessResponse) -> str:
    decision = response.overall_decision or "未知"
    risk_text = _format_risks(response.risk_reasons)
    advice_text = _format_advice(response)
    execute_text = "可以执行" if response.allow_execute else "不建议直接执行"
    return f"本次任务整体结论为{decision}，当前{execute_text}。主要依据是{risk_text}。{advice_text}"


def _explain_recommendation(response: UnifiedBusinessResponse) -> str:
    if not response.recommended_windows:
        advice_text = _format_advice(response)
        return f"当前没有找到满足最小时长要求的推荐窗口。主要风险包括{_format_risks(response.risk_reasons)}。{advice_text}"

    top_window = response.recommended_windows[0]
    risk_text = _format_risks(top_window.reasons or response.risk_reasons)
    advice_text = _format_advice(response)
    return (
        f"当前优先推荐 {top_window.start_time} 到 {top_window.end_time} 执行任务，"
        f"连续时长 {top_window.duration_hours} 小时，结论为{top_window.overall_decision}。"
        f"推荐依据是{risk_text}。{advice_text}"
    )


def _explain_comparison(response: UnifiedBusinessResponse) -> str:
    if not response.ranked_locations:
        return "当前多地点比选没有得到可排序结果，建议检查地点、日期和时间段是否完整。"

    top_location = response.ranked_locations[0]
    risk_text = _format_risks(response.risk_reasons)
    advice_text = _format_advice(response)
    return (
        f"当前多地点比选排名第一的是{top_location.location}，综合得分为{top_location.score}。"
        f"该地点可飞小时数为{top_location.flyable_hour_count}，最长连续可飞"
        f"{top_location.max_continuous_flyable_hours}小时。主要依据是{risk_text}。{advice_text}"
    )


def _explain_history(response: UnifiedBusinessResponse) -> str:
    if not response.history_summary:
        return response.summary

    history = response.history_summary
    risk_text = _format_risks(response.risk_reasons)
    advice_text = _format_advice(response)
    return (
        f"历史任务 {history.request_id} 的结论为{history.overall_decision}，"
        f"地点为{history.location}，时间为{history.date} {history.start_time}-{history.end_time}。"
        f"主要依据是{risk_text}。{advice_text}"
    )


def _format_risks(risk_reasons: list[str]) -> str:
    if not risk_reasons:
        return "未发现明显高风险因素"
    return "、".join(risk_reasons[:5])


def _format_advice(response: UnifiedBusinessResponse) -> str:
    advice_items = response.details.get("advice") if response.details else None
    if not isinstance(advice_items, list) or not advice_items:
        return "建议执行前继续关注最新天气和预警变化。"

    texts: list[str] = []
    for item in advice_items[:3]:
        if not isinstance(item, dict):
            continue
        advice_text = item.get("advice_text")
        if isinstance(advice_text, str) and advice_text.strip():
            texts.append(advice_text.strip())

    if not texts:
        return "建议执行前继续关注最新天气和预警变化。"
    return "操作建议：" + "；".join(texts) + "。"
