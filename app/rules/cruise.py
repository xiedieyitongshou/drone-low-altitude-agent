from app.schemas.assessment import CruiseAssessmentAdvice, HourlyAssessment, RiskDecision, RuleHit
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
    rule_hits: list[RuleHit] = []
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
        _append_rule_hit(
            risk_factors,
            rule_hits,
            metric="weather_text",
            operator="in",
            actual_value=weather_text,
            threshold=sorted(hourly_rules.prohibited_weather_texts),
            decision=RiskDecision.PROHIBITED,
            label=f"天气为{weather_text}",
            risk_tag="severe_weather",
        )
    if precip is not None and precip >= hourly_rules.prohibited_precip_mm:
        _append_rule_hit(
            risk_factors,
            rule_hits,
            metric="precip",
            operator=">=",
            actual_value=precip,
            threshold=hourly_rules.prohibited_precip_mm,
            unit="mm",
            decision=RiskDecision.PROHIBITED,
            label="降水量偏高",
            risk_tag="precipitation",
        )
    if pop is not None and pop >= hourly_rules.prohibited_pop_percent:
        _append_rule_hit(
            risk_factors,
            rule_hits,
            metric="pop",
            operator=">=",
            actual_value=pop,
            threshold=hourly_rules.prohibited_pop_percent,
            unit="%",
            decision=RiskDecision.PROHIBITED,
            label="降水概率高",
            risk_tag="precipitation_probability",
        )
    if wind_speed is not None and wind_speed >= hourly_rules.prohibited_wind_speed_kmh:
        _append_rule_hit(
            risk_factors,
            rule_hits,
            metric="wind_speed",
            operator=">=",
            actual_value=wind_speed,
            threshold=hourly_rules.prohibited_wind_speed_kmh,
            unit="km/h",
            decision=RiskDecision.PROHIBITED,
            label="风速偏高",
            risk_tag="high_wind",
        )
    if wind_scale_upper is not None and wind_scale_upper >= hourly_rules.prohibited_wind_scale_upper:
        _append_rule_hit(
            risk_factors,
            rule_hits,
            metric="wind_scale",
            operator=">=",
            actual_value=wind_scale_upper,
            threshold=hourly_rules.prohibited_wind_scale_upper,
            unit="level",
            decision=RiskDecision.PROHIBITED,
            label="风力等级过高",
            risk_tag="high_wind",
        )

    if risk_factors:
        decision = RiskDecision.PROHIBITED
        return _build_hourly_assessment(hour, decision, risk_factors, rule_hits)

    if weather_text in hourly_rules.caution_weather_texts:
        _append_rule_hit(
            risk_factors,
            rule_hits,
            metric="weather_text",
            operator="in",
            actual_value=weather_text,
            threshold=sorted(hourly_rules.caution_weather_texts),
            decision=RiskDecision.CAUTION,
            label=f"天气为{weather_text}",
            risk_tag="cloudy_or_light_rain",
        )
    if precip is not None and hourly_rules.caution_precip_min_mm < precip < hourly_rules.caution_precip_max_mm:
        _append_rule_hit(
            risk_factors,
            rule_hits,
            metric="precip",
            operator="range",
            actual_value=precip,
            threshold=[hourly_rules.caution_precip_min_mm, hourly_rules.caution_precip_max_mm],
            unit="mm",
            decision=RiskDecision.CAUTION,
            label="存在轻中度降水",
            risk_tag="precipitation",
        )
    if pop is not None and hourly_rules.caution_pop_min_percent <= pop < hourly_rules.caution_pop_max_percent:
        _append_rule_hit(
            risk_factors,
            rule_hits,
            metric="pop",
            operator="range",
            actual_value=pop,
            threshold=[hourly_rules.caution_pop_min_percent, hourly_rules.caution_pop_max_percent],
            unit="%",
            decision=RiskDecision.CAUTION,
            label="降水概率中等",
            risk_tag="precipitation_probability",
        )
    if wind_speed is not None and hourly_rules.caution_wind_speed_min_kmh <= wind_speed < hourly_rules.caution_wind_speed_max_kmh:
        _append_rule_hit(
            risk_factors,
            rule_hits,
            metric="wind_speed",
            operator="range",
            actual_value=wind_speed,
            threshold=[hourly_rules.caution_wind_speed_min_kmh, hourly_rules.caution_wind_speed_max_kmh],
            unit="km/h",
            decision=RiskDecision.CAUTION,
            label="风速中等偏高",
            risk_tag="high_wind",
        )
    if wind_scale_upper is not None and wind_scale_upper == hourly_rules.caution_wind_scale_upper:
        _append_rule_hit(
            risk_factors,
            rule_hits,
            metric="wind_scale",
            operator="==",
            actual_value=wind_scale_upper,
            threshold=hourly_rules.caution_wind_scale_upper,
            unit="level",
            decision=RiskDecision.CAUTION,
            label="风力等级中等",
            risk_tag="high_wind",
        )
    if humidity is not None and humidity >= hourly_rules.caution_humidity_percent:
        _append_rule_hit(
            risk_factors,
            rule_hits,
            metric="humidity",
            operator=">=",
            actual_value=humidity,
            threshold=hourly_rules.caution_humidity_percent,
            unit="%",
            decision=RiskDecision.CAUTION,
            label="湿度较高",
            risk_tag="high_humidity",
        )

    if risk_factors:
        decision = RiskDecision.CAUTION

    return _build_hourly_assessment(hour, decision, risk_factors, rule_hits)


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
    matched_warning_hits = [
        _build_warning_rule_hit(warning.event_type, warning.warning_level)
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
                    "rule_hits": _merge_rule_hits(
                        assessment.rule_hits,
                        _rule_hits_for_hour(matched_warning_hits, assessment.fx_time),
                    ),
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
                            "rule_hits": _merge_rule_hits(
                                assessment.rule_hits,
                                _rule_hits_for_hour(matched_warning_hits, assessment.fx_time),
                            ),
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
        rule_hits=_collect_rule_hits(hourly_assessment),
        hourly_assessment=hourly_assessment,
    )


def _build_hourly_assessment(
    hour: WeatherHourData,
    decision: RiskDecision,
    risk_factors: list[str],
    rule_hits: list[RuleHit],
) -> HourlyAssessment:
    hourly_rule_hits = [hit.model_copy(update={"fx_time": hour.fx_time}) for hit in rule_hits]
    return HourlyAssessment(
        fx_time=hour.fx_time,
        decision=decision,
        risk_factors=risk_factors,
        rule_hits=hourly_rule_hits,
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
        lower, upper = text.split("-", 1)
        try:
            lower_scale = int(lower)
            upper_scale = int(upper)
        except ValueError:
            return None
        if lower_scale == 1 and upper_scale == 3:
            return 2
        return upper_scale
    try:
        wind_scale = int(text)
    except ValueError:
        return None
    return wind_scale


def _append_rule_hit(
    risk_factors: list[str],
    rule_hits: list[RuleHit],
    *,
    metric: str,
    operator: str,
    actual_value: str | float | int | None,
    threshold: str | float | int | list[str | float | int] | None,
    decision: RiskDecision,
    label: str,
    risk_tag: str,
    unit: str | None = None,
) -> None:
    risk_factors.append(label)
    rule_hits.append(
        RuleHit(
            metric=metric,
            operator=operator,
            actual_value=actual_value,
            threshold=threshold,
            unit=unit,
            decision=decision,
            label=label,
            risk_tag=risk_tag,
        )
    )


def _build_warning_message(event_type: str | None, warning_level: str | None) -> str:
    level = (warning_level or "").lower()
    return f"高风险预警：{event_type}{level}"


def _build_warning_rule_hit(event_type: str | None, warning_level: str | None) -> RuleHit:
    level = (warning_level or "").lower()
    decision = RiskDecision.PROHIBITED if level in {"orange", "red"} else RiskDecision.CAUTION
    return RuleHit(
        metric="warning_type",
        operator="in",
        actual_value=event_type,
        threshold=event_type,
        unit=None,
        decision=decision,
        label=_build_warning_message(event_type, warning_level),
        risk_tag="weather_warning",
    )


def _merge_risk_factors(existing: list[str], additions: list[str]) -> list[str]:
    merged = list(existing)
    for item in additions:
        if item not in merged:
            merged.append(item)
    return merged


def _merge_rule_hits(existing: list[RuleHit], additions: list[RuleHit]) -> list[RuleHit]:
    merged = list(existing)
    seen = {_rule_hit_key(item) for item in merged}
    for item in additions:
        key = _rule_hit_key(item)
        if key not in seen:
            merged.append(item)
            seen.add(key)
    return merged


def _rule_hits_for_hour(rule_hits: list[RuleHit], fx_time: str) -> list[RuleHit]:
    return [hit.model_copy(update={"fx_time": fx_time}) for hit in rule_hits]


def _collect_rule_hits(hourly_assessment: list[HourlyAssessment]) -> list[RuleHit]:
    collected: list[RuleHit] = []
    for assessment in hourly_assessment:
        collected.extend(assessment.rule_hits)
    return collected


def _rule_hit_key(item: RuleHit) -> tuple[object, ...]:
    threshold = item.threshold
    if isinstance(threshold, list):
        threshold = tuple(threshold)
    return (
        item.metric,
        item.operator,
        item.actual_value,
        threshold,
        item.unit,
        item.decision,
        item.label,
        item.risk_tag,
    )
