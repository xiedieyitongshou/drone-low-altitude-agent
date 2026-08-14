from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable


NUMERIC_METRICS = {
    "precip": {"unit": "mm", "min": 0.0, "max": 500.0},
    "pop": {"unit": "%", "min": 0.0, "max": 100.0},
    "wind_speed": {"unit": "km/h", "min": 0.0, "max": 250.0},
    "wind_scale": {"unit": "level", "min": 0.0, "max": 17.0},
    "humidity": {"unit": "%", "min": 0.0, "max": 100.0},
    "visibility": {"unit": "km", "min": 0.0, "max": 100.0},
}

TEXT_METRICS = {
    "weather_text",
    "warning_level",
    "warning_type",
}

METRIC_WHITELIST = set(NUMERIC_METRICS) | TEXT_METRICS
OPERATOR_WHITELIST = {">=", "==", "in"}
DECISION_WHITELIST = {"适飞", "慎飞", "禁飞"}

NUMERIC_OPERATORS = {">="}
TEXT_OPERATORS = {"==", "in"}


@dataclass(frozen=True)
class RuleValidationIssue:
    code: str
    message: str
    item_index: int | None = None
    metric: str | None = None


@dataclass
class RuleValidationResult:
    issues: list[RuleValidationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.issues

    @property
    def messages(self) -> list[str]:
        return [issue.message for issue in self.issues]

    def add(self, code: str, message: str, *, item_index: int | None = None, metric: str | None = None) -> None:
        self.issues.append(
            RuleValidationIssue(
                code=code,
                message=message,
                item_index=item_index,
                metric=metric,
            )
        )


def validate_rule_set(items: Iterable[Any]) -> RuleValidationResult:
    result = RuleValidationResult()
    item_list = list(items)
    enabled_items = [item for item in item_list if _get_bool(item, "enabled", default=True)]

    if not enabled_items:
        result.add("NO_ENABLED_RULE", "规则集至少需要包含一条启用规则")

    for index, item in enumerate(item_list):
        validate_rule_item(item, result=result, item_index=index)

    _validate_threshold_conflicts(enabled_items, result)
    return result


def validate_rule_item(
    item: Any,
    *,
    result: RuleValidationResult | None = None,
    item_index: int | None = None,
) -> RuleValidationResult:
    validation = result or RuleValidationResult()

    metric = _normalize_value(_get_value(item, "metric"))
    operator = _normalize_value(_get_value(item, "operator"))
    decision = _normalize_value(_get_value(item, "decision"))
    unit = _normalize_value(_get_value(item, "unit"))
    threshold_value = _get_value(item, "threshold_value")
    threshold_text = _normalize_value(_get_value(item, "threshold_text"))
    threshold_values = _get_threshold_values(item)

    if metric not in METRIC_WHITELIST:
        validation.add(
            "INVALID_METRIC",
            f"非法规则字段：{metric or '<empty>'}",
            item_index=item_index,
            metric=metric,
        )
        return validation

    if operator not in OPERATOR_WHITELIST:
        validation.add(
            "INVALID_OPERATOR",
            f"非法操作符：{operator or '<empty>'}",
            item_index=item_index,
            metric=metric,
        )
    elif metric in NUMERIC_METRICS and operator not in NUMERIC_OPERATORS:
        validation.add(
            "INVALID_NUMERIC_OPERATOR",
            f"数值指标 {metric} 仅支持 >= 操作符",
            item_index=item_index,
            metric=metric,
        )
    elif metric in TEXT_METRICS and operator not in TEXT_OPERATORS:
        validation.add(
            "INVALID_TEXT_OPERATOR",
            f"文本指标 {metric} 仅支持 == 或 in 操作符",
            item_index=item_index,
            metric=metric,
        )

    if decision not in DECISION_WHITELIST:
        validation.add(
            "INVALID_DECISION",
            f"非法规则结论：{decision or '<empty>'}",
            item_index=item_index,
            metric=metric,
        )

    if metric in NUMERIC_METRICS:
        _validate_numeric_threshold(
            metric=metric,
            unit=unit,
            threshold_value=threshold_value,
            validation=validation,
            item_index=item_index,
        )
    else:
        _validate_text_threshold(
            metric=metric,
            operator=operator,
            threshold_text=threshold_text,
            threshold_values=threshold_values,
            unit=unit,
            validation=validation,
            item_index=item_index,
        )

    return validation


def _validate_numeric_threshold(
    *,
    metric: str,
    unit: str,
    threshold_value: Any,
    validation: RuleValidationResult,
    item_index: int | None,
) -> None:
    spec = NUMERIC_METRICS[metric]
    expected_unit = str(spec["unit"])
    if unit != expected_unit:
        validation.add(
            "INVALID_UNIT",
            f"指标 {metric} 的单位必须是 {expected_unit}",
            item_index=item_index,
            metric=metric,
        )

    value = _to_float(threshold_value)
    if value is None:
        validation.add(
            "MISSING_NUMERIC_THRESHOLD",
            f"数值指标 {metric} 必须提供 threshold_value",
            item_index=item_index,
            metric=metric,
        )
        return

    min_value = float(spec["min"])
    max_value = float(spec["max"])
    if value < min_value or value > max_value:
        validation.add(
            "THRESHOLD_OUT_OF_RANGE",
            f"指标 {metric} 的阈值 {value:g} 超出范围 [{min_value:g}, {max_value:g}]",
            item_index=item_index,
            metric=metric,
        )


def _validate_text_threshold(
    *,
    metric: str,
    operator: str,
    threshold_text: str,
    threshold_values: list[Any],
    unit: str,
    validation: RuleValidationResult,
    item_index: int | None,
) -> None:
    if unit:
        validation.add(
            "INVALID_UNIT",
            f"文本指标 {metric} 不应配置单位",
            item_index=item_index,
            metric=metric,
        )

    if operator == "==" and not threshold_text:
        validation.add(
            "MISSING_TEXT_THRESHOLD",
            f"文本指标 {metric} 使用 == 时必须提供 threshold_text",
            item_index=item_index,
            metric=metric,
        )
    if operator == "in":
        cleaned_values = [_normalize_value(value) for value in threshold_values]
        if not cleaned_values or any(not value for value in cleaned_values):
            validation.add(
                "MISSING_TEXT_THRESHOLD_VALUES",
                f"文本指标 {metric} 使用 in 时必须提供非空 threshold_values",
                item_index=item_index,
                metric=metric,
            )


def _validate_threshold_conflicts(items: list[Any], result: RuleValidationResult) -> None:
    thresholds: dict[tuple[str, str], dict[str, float]] = {}

    for item in items:
        metric = _normalize_value(_get_value(item, "metric"))
        operator = _normalize_value(_get_value(item, "operator"))
        decision = _normalize_value(_get_value(item, "decision"))
        unit = _normalize_value(_get_value(item, "unit"))
        value = _to_float(_get_value(item, "threshold_value"))

        if metric not in NUMERIC_METRICS or operator != ">=" or value is None:
            continue
        if decision not in {"慎飞", "禁飞"}:
            continue

        key = (metric, unit)
        thresholds.setdefault(key, {})[decision] = value

    for (metric, _unit), decisions in thresholds.items():
        caution_value = decisions.get("慎飞")
        prohibited_value = decisions.get("禁飞")
        if caution_value is None or prohibited_value is None:
            continue
        if caution_value >= prohibited_value:
            result.add(
                "CONFLICTING_THRESHOLDS",
                f"指标 {metric} 的慎飞阈值 {caution_value:g} 必须小于禁飞阈值 {prohibited_value:g}",
                metric=metric,
            )


def _get_value(item: Any, field_name: str) -> Any:
    if isinstance(item, dict):
        return item.get(field_name)
    return getattr(item, field_name, None)


def _get_bool(item: Any, field_name: str, *, default: bool) -> bool:
    value = _get_value(item, field_name)
    return default if value is None else bool(value)


def _get_threshold_values(item: Any) -> list[Any]:
    values = _get_value(item, "threshold_values")
    if values is None:
        values = _get_value(item, "threshold_values_json")
    if values is None:
        return []
    return values if isinstance(values, list) else [values]


def _normalize_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Enum):
        return str(value.value).strip()
    return str(value).strip()


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
