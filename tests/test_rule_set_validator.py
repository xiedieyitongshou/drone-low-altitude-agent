from app.rules.rule_set_validator import validate_rule_set
from app.schemas.rule_set import RuleDecision, RuleItemCreate, RuleOperator


def build_rule(**overrides):
    payload = {
        "metric": "wind_speed",
        "operator": RuleOperator.GREATER_THAN_OR_EQUAL,
        "threshold_value": 25.0,
        "unit": "km/h",
        "decision": RuleDecision.PROHIBITED,
        "label": "风速禁飞阈值",
        "risk_tag": "high_wind",
        "priority": 10,
        "enabled": True,
    }
    payload.update(overrides)
    return RuleItemCreate(**payload)


def test_valid_numeric_and_text_rules_pass():
    result = validate_rule_set(
        [
            build_rule(),
            build_rule(
                metric="weather_text",
                operator=RuleOperator.IN,
                threshold_value=None,
                threshold_values=["雷雨", "暴雨"],
                unit=None,
                decision=RuleDecision.PROHIBITED,
                label="高风险天气",
            ),
        ]
    )

    assert result.is_valid
    assert result.messages == []


def test_invalid_metric_is_rejected():
    result = validate_rule_set(
        [
            {
                "metric": "python_expression",
                "operator": ">=",
                "threshold_value": 1,
                "unit": "km/h",
                "decision": "禁飞",
                "label": "非法字段",
                "enabled": True,
            }
        ]
    )

    assert not result.is_valid
    assert "INVALID_METRIC" in {issue.code for issue in result.issues}


def test_invalid_operator_is_rejected():
    result = validate_rule_set(
        [
            {
                "metric": "wind_speed",
                "operator": "<",
                "threshold_value": 25,
                "unit": "km/h",
                "decision": "禁飞",
                "label": "非法操作符",
                "enabled": True,
            }
        ]
    )

    assert not result.is_valid
    assert "INVALID_OPERATOR" in {issue.code for issue in result.issues}


def test_invalid_decision_is_rejected():
    result = validate_rule_set(
        [
            {
                "metric": "wind_speed",
                "operator": ">=",
                "threshold_value": 25,
                "unit": "km/h",
                "decision": "强制放行",
                "label": "非法结论",
                "enabled": True,
            }
        ]
    )

    assert not result.is_valid
    assert "INVALID_DECISION" in {issue.code for issue in result.issues}


def test_numeric_range_and_unit_are_validated():
    result = validate_rule_set(
        [
            {
                "metric": "pop",
                "operator": ">=",
                "threshold_value": 120,
                "unit": "mm",
                "decision": "禁飞",
                "label": "降水概率非法阈值",
                "enabled": True,
            }
        ]
    )

    codes = {issue.code for issue in result.issues}
    assert "INVALID_UNIT" in codes
    assert "THRESHOLD_OUT_OF_RANGE" in codes


def test_text_rule_requires_text_thresholds_and_no_unit():
    result = validate_rule_set(
        [
            {
                "metric": "weather_text",
                "operator": "in",
                "threshold_values": [],
                "unit": "mm",
                "decision": "禁飞",
                "label": "文本规则脏数据",
                "enabled": True,
            }
        ]
    )

    codes = {issue.code for issue in result.issues}
    assert "INVALID_UNIT" in codes
    assert "MISSING_TEXT_THRESHOLD_VALUES" in codes


def test_rule_set_requires_at_least_one_enabled_rule():
    result = validate_rule_set([build_rule(enabled=False)])

    assert not result.is_valid
    assert "NO_ENABLED_RULE" in {issue.code for issue in result.issues}


def test_conflicting_caution_and_prohibited_thresholds_are_rejected():
    result = validate_rule_set(
        [
            build_rule(
                threshold_value=25,
                decision=RuleDecision.CAUTION,
                label="风速慎飞阈值",
            ),
            build_rule(
                threshold_value=20,
                decision=RuleDecision.PROHIBITED,
                label="风速禁飞阈值",
            ),
        ]
    )

    assert not result.is_valid
    assert "CONFLICTING_THRESHOLDS" in {issue.code for issue in result.issues}
