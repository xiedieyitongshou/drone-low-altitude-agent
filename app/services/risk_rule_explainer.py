from typing import Any

from app.rules.mission_profiles import get_mission_rule_profile, list_supported_task_types


def explain_risk_rules(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    task_type = str(payload.get("task_type") or "cruise")
    profile = get_mission_rule_profile(task_type)
    hourly = profile.hourly
    warning = profile.warning
    risk_reasons = _normalize_list(payload.get("risk_reasons"))
    overall_decision = payload.get("overall_decision")

    return {
        "task_type": profile.task_type,
        "display_name": profile.display_name,
        "description": profile.description,
        "overall_decision": overall_decision,
        "risk_reasons": risk_reasons,
        "rule_source": "app.rules.mission_profiles + app.rules.cruise",
        "decision_logic": {
            "prohibited": "任一小时触发禁飞天气、降水概率、降水量、风速、风力等级或橙/红色高风险预警时，整体结论为禁飞。",
            "caution": "未触发禁飞但存在慎飞天气、轻中度降水、中等降水概率、中等偏高风速、较高湿度或黄色高风险预警时，整体结论为慎飞。",
            "suitable": "所有小时均未命中禁飞和慎飞条件时，整体结论为适飞。",
        },
        "hourly_thresholds": {
            "prohibited_weather_texts": sorted(hourly.prohibited_weather_texts),
            "caution_weather_texts": sorted(hourly.caution_weather_texts),
            "prohibited_precip_mm": hourly.prohibited_precip_mm,
            "prohibited_pop_percent": hourly.prohibited_pop_percent,
            "prohibited_wind_speed_kmh": hourly.prohibited_wind_speed_kmh,
            "prohibited_wind_scale_upper": hourly.prohibited_wind_scale_upper,
            "caution_precip_range_mm": [hourly.caution_precip_min_mm, hourly.caution_precip_max_mm],
            "caution_pop_range_percent": [hourly.caution_pop_min_percent, hourly.caution_pop_max_percent],
            "caution_wind_speed_range_kmh": [hourly.caution_wind_speed_min_kmh, hourly.caution_wind_speed_max_kmh],
            "caution_wind_scale_upper": hourly.caution_wind_scale_upper,
            "caution_humidity_percent": hourly.caution_humidity_percent,
        },
        "warning_rules": {
            "high_risk_warning_types": sorted(warning.high_risk_warning_types),
            "force_prohibited_levels": sorted(warning.force_prohibited_levels),
            "upgrade_to_caution_levels": sorted(warning.upgrade_to_caution_levels),
        },
        "matched_explanation": _build_matched_explanation(overall_decision, risk_reasons),
        "supported_task_types": list(list_supported_task_types()),
    }


def _build_matched_explanation(overall_decision: object, risk_reasons: list[str]) -> str:
    if risk_reasons:
        return f"本次解释基于已识别风险原因：{'；'.join(risk_reasons[:5])}。"
    if overall_decision:
        return f"当前只拿到整体结论 {overall_decision}，没有拿到逐小时风险因子，因此返回规则来源和阈值说明。"
    return "当前没有具体评估结果上下文，因此返回规则来源、任务阈值和整体判定逻辑。"


def _normalize_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []
