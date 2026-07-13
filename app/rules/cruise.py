from app.schemas.assessment import CruiseAssessmentAdvice, HourlyAssessment, RiskDecision
from app.schemas.warning import WarningDataBundle
from app.schemas.weather import WeatherHourData
from app.rules.mission_profiles import MissionRuleProfile, get_mission_rule_profile


def assess_cruise_window(
    hourly_weather: list[WeatherHourData],
    warnings: WarningDataBundle | None = None,
    task_type: str = "cruise",
) -> CruiseAssessmentAdvice:
    profile = get_mission_rule_profile(task_type)
    hourly_assessment = [assess_hourly_weather(hour, profile=profile) for hour in hourly_weather]
    if warnings is not None:
        hourly_assessment = apply_warning_adjustments(hourly_assessment, warnings, profile=profile)
    return summarize_assessment(hourly_assessment)


def assess_hourly_weather(
    hour: WeatherHourData,
    *,
    profile: MissionRuleProfile | None = None,
    task_type: str = "cruise",
) -> HourlyAssessment:
    risk_factors: list[str] = []
    decision = RiskDecision.SUITABLE
    active_profile = profile or get_mission_rule_profile(task_type)
    hourly_rules = active_profile.hourly

    weather_text = (hour.text or "").strip()
    precip = _to_float(hour.precip)
    pop = _to_float(hour.pop)
    wind_speed = _to_float(hour.wind_speed)
    humidity = _to_float(hour.humidity)
    wind_scale_upper = _parse_wind_scale_upper(hour.wind_scale)

    if weather_text in hourly_rules.prohibited_weather_texts:
        risk_factors.append(f"天气为{weather_text}")
    if precip is not None and precip >= hourly_rules.prohibited_precip_mm:
        risk_factors.append("降水量偏高")
    if pop is not None and pop >= hourly_rules.prohibited_pop_percent:
        risk_factors.append("降水概率高")
    if wind_speed is not None and wind_speed >= hourly_rules.prohibited_wind_speed_ms:
        risk_factors.append("风速偏高")
    if wind_scale_upper is not None and wind_scale_upper >= hourly_rules.prohibited_wind_scale_upper:
        risk_factors.append("风力等级过高")

    if risk_factors:
        decision = RiskDecision.PROHIBITED
        return _build_hourly_assessment(hour, decision, risk_factors)

    if weather_text in hourly_rules.caution_weather_texts:
        risk_factors.append(f"天气为{weather_text}")
    if precip is not None and hourly_rules.caution_precip_min_mm < precip < hourly_rules.caution_precip_max_mm:
        risk_factors.append("存在轻中度降水")
    if pop is not None and hourly_rules.caution_pop_min_percent <= pop < hourly_rules.caution_pop_max_percent:
        risk_factors.append("降水概率中等")
    if wind_speed is not None and hourly_rules.caution_wind_speed_min_ms <= wind_speed < hourly_rules.caution_wind_speed_max_ms:
        risk_factors.append("风速中等偏高")
    if wind_scale_upper is not None and wind_scale_upper == hourly_rules.caution_wind_scale_upper:
        risk_factors.append("风力等级中等")
    if humidity is not None and humidity >= hourly_rules.caution_humidity_percent:
        risk_factors.append("湿度较高")

    if risk_factors:
        decision = RiskDecision.CAUTION

    return _build_hourly_assessment(hour, decision, risk_factors)


def apply_warning_adjustments(
    hourly_assessment: list[HourlyAssessment],
    warnings: WarningDataBundle,
    *,
    profile: MissionRuleProfile | None = None,
    task_type: str = "cruise",
) -> list[HourlyAssessment]:
    active_profile = profile or get_mission_rule_profile(task_type)
    warning_rules = active_profile.warning
    if not warnings.has_warning or not warnings.warnings:
        return hourly_assessment

    matched_warning_messages = [
        _build_warning_message(warning.event_type, warning.warning_level)
        for warning in warnings.warnings
        if (warning.event_type or "") in warning_rules.high_risk_warning_types and (warning.warning_level or "").lower()
    ]
    if not matched_warning_messages:
        return hourly_assessment

    warning_levels = {
        (warning.warning_level or "").lower()
        for warning in warnings.warnings
        if (warning.event_type or "") in warning_rules.high_risk_warning_types
    }
    if warning_levels & warning_rules.force_prohibited_levels:
        return [
            assessment.model_copy(
                update={
                    "decision": RiskDecision.PROHIBITED,
                    "risk_factors": _merge_risk_factors(assessment.risk_factors, matched_warning_messages),
                }
            )
            for assessment in hourly_assessment
        ]

    if warning_levels & warning_rules.upgrade_to_caution_levels:
        adjusted: list[HourlyAssessment] = []
        for assessment in hourly_assessment:
            if assessment.decision == RiskDecision.SUITABLE:
                adjusted.append(
                    assessment.model_copy(
                        update={
                            "decision": RiskDecision.CAUTION,
                            "risk_factors": _merge_risk_factors(assessment.risk_factors, matched_warning_messages),
                        }
                    )
                )
            else:
                adjusted.append(assessment)
        return adjusted

    return hourly_assessment


def summarize_assessment(hourly_assessment: list[HourlyAssessment]) -> CruiseAssessmentAdvice:
    overall_decision = RiskDecision.SUITABLE
    if any(item.decision == RiskDecision.PROHIBITED for item in hourly_assessment):
        overall_decision = RiskDecision.PROHIBITED
    elif any(item.decision == RiskDecision.CAUTION for item in hourly_assessment):
        overall_decision = RiskDecision.CAUTION

    summary_risk_factors = [
        f"{item.fx_time} 风险较高：{'；'.join(item.risk_factors)}"
        for item in hourly_assessment
        if item.risk_factors
    ]

    return CruiseAssessmentAdvice(
        allow_cruise=overall_decision == RiskDecision.SUITABLE,
        overall_decision=overall_decision,
        summary_risk_factors=summary_risk_factors,
        hourly_assessment=hourly_assessment,
    )


def _build_hourly_assessment(
    hour: WeatherHourData,
    decision: RiskDecision,
    risk_factors: list[str],
) -> HourlyAssessment:
    return HourlyAssessment(
        fx_time=hour.fx_time,
        decision=decision,
        risk_factors=risk_factors,
        weather={
            "temp": hour.temp,
            "text": hour.text,
            "wind_scale": hour.wind_scale,
            "wind_speed": hour.wind_speed,
            "humidity": hour.humidity,
            "precip": hour.precip,
            "pop": hour.pop,
            "pressure": hour.pressure,
            "cloud": hour.cloud,
        },
    )


def _to_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_wind_scale_upper(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    text = value.strip()
    if "-" in text:
        _, upper = text.split("-", 1)
        try:
            return int(upper)
        except ValueError:
            return None
    try:
        return int(text)
    except ValueError:
        return None


def _build_warning_message(event_type: str | None, warning_level: str | None) -> str:
    level = (warning_level or "").lower()
    return f"高风险预警：{event_type}{level}"


def _merge_risk_factors(existing: list[str], additions: list[str]) -> list[str]:
    merged = list(existing)
    for item in additions:
        if item not in merged:
            merged.append(item)
    return merged
