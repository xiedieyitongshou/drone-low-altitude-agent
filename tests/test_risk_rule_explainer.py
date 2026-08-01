from app.services.risk_rule_explainer import explain_risk_rules


def test_explain_risk_rules_returns_thresholds_and_source():
    result = explain_risk_rules(
        {
            "task_type": "inspection",
            "overall_decision": "禁飞",
            "risk_reasons": ["风速偏高"],
        }
    )

    assert result["task_type"] == "inspection"
    assert result["display_name"] == "设备巡检"
    assert result["rule_source"] == "app.rules.mission_profiles + app.rules.cruise"
    assert result["hourly_thresholds"]["prohibited_wind_speed_kmh"] == 25
    assert result["warning_rules"]["force_prohibited_levels"] == ["orange", "red"]
    assert "风速偏高" in result["matched_explanation"]


def test_explain_risk_rules_falls_back_to_cruise_for_unknown_task_type():
    result = explain_risk_rules({"task_type": "unknown"})

    assert result["task_type"] == "cruise"
    assert "cruise" in result["supported_task_types"]
