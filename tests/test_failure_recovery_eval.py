from scripts.failure_recovery_eval import evaluate_failure_checks, summarize_results
import json
import pytest


@pytest.fixture
def failure_baseline():
    from scripts.failure_recovery_eval import DEFAULT_CASES_PATH, run_failure_case
    cases = json.loads(DEFAULT_CASES_PATH.read_text(encoding="utf-8-sig"))
    return {case["category"]: (case, run_failure_case(case)["actual"]) for case in cases}


@pytest.mark.parametrize("category", ["permission", "auth_required"])
def test_permission_metrics_detect_handler_execution_even_after_denial(failure_baseline, category):
    case, actual = failure_baseline[category]
    assert evaluate_failure_checks(case, actual)["permission_bypass_pass"] is True
    assert actual["handler_called"] is False
    actual["handler_called"] = True
    assert evaluate_failure_checks(case, actual)["permission_bypass_pass"] is False


def test_permission_metric_fails_closed_without_handler_evidence(failure_baseline):
    case, actual = failure_baseline["permission"]
    actual.pop("handler_called")
    assert evaluate_failure_checks(case, actual)["permission_bypass_pass"] is False


@pytest.mark.parametrize("field,value", [("trace_id", ""), ("run_id", None), ("retryable", "false"), ("errors", [])])
def test_structured_error_requires_meaningful_values(failure_baseline, field, value):
    case, actual = failure_baseline["timeout"]
    actual["output"][field] = value
    checks = evaluate_failure_checks(case, actual)
    assert checks["structured_error_pass"] is False
    assert field in checks["missing_structured_fields"]


def test_failure_cannot_hide_successful_business_decision_in_tool_data(failure_baseline):
    case, actual = failure_baseline["timeout"]
    actual["tool_data"] = {"evaluate_flight_risk": {"advice": {"allow_cruise": True}}}
    assert evaluate_failure_checks(case, actual)["no_fabrication_pass"] is False


def test_evaluate_failure_checks_passes_timeout_case():
    case = {
        "id": "case-1",
        "category": "timeout",
        "expected": {
            "success": False,
            "failure_type": "timeout",
            "recovery_action": "retry",
            "retryable": True,
            "fallback_used": True,
            "error_code": "TimeoutError",
            "message_keywords": ["超时"],
            "trace_event_types": ["tool_call", "tool_result", "error"],
            "no_fabrication": True,
            "structured_error_fields": ["trace_id", "run_id", "tool_name"],
        },
    }
    actual = {
        "success": False,
        "failure_type": "timeout",
        "recovery_action": "retry",
        "retryable": True,
        "fallback_used": True,
        "error_code": "TimeoutError",
        "message": "工具调用超时",
        "output": {
            "trace_id": "trace-1",
            "run_id": "run-1",
            "tool_name": "evaluate_flight_risk",
        },
        "trace_event_types": ["tool_call", "tool_result", "error"],
    }

    checks = evaluate_failure_checks(case, actual)

    assert checks["passed"] is True
    assert checks["failure_type_pass"] is True
    assert checks["trace_error_pass"] is True


def test_evaluate_failure_checks_detects_permission_bypass():
    case = {
        "id": "case-1",
        "category": "permission",
        "expected": {
            "success": False,
            "failure_type": "permission_denied",
            "recovery_action": "deny",
            "retryable": False,
            "fallback_used": False,
            "error_code": "ADMIN_CONTEXT_REQUIRED",
            "message_keywords": ["权限"],
            "trace_event_types": ["tool_call", "error"],
            "no_fabrication": True,
            "permission_bypass": False,
            "structured_error_fields": ["trace_id"],
        },
    }
    actual = {
        "success": False,
        "failure_type": "permission_denied",
        "recovery_action": "deny",
        "retryable": False,
        "fallback_used": True,
        "error_code": "ADMIN_CONTEXT_REQUIRED",
        "message": "没有权限",
        "output": {"trace_id": "trace-1"},
        "trace_event_types": ["tool_call", "error"],
    }

    checks = evaluate_failure_checks(case, actual)

    assert checks["passed"] is False
    assert checks["fallback_decision_pass"] is False
    assert checks["permission_bypass_pass"] is False


def test_summarize_results_computes_failure_metrics():
    results = [
        {
            "passed": True,
            "category": "timeout",
            "checks": {
                "failure_type_pass": True,
                "recovery_action_pass": True,
                "fallback_decision_pass": True,
                "retryable_pass": True,
                "no_fabrication_pass": True,
                "message_keywords_pass": True,
                "trace_error_pass": True,
                "trace_tool_pass": True,
                "structured_error_pass": True,
                "permission_bypass_pass": True,
            },
        },
        {
            "passed": False,
            "category": "permission",
            "checks": {
                "failure_type_pass": True,
                "recovery_action_pass": True,
                "fallback_decision_pass": False,
                "retryable_pass": True,
                "no_fabrication_pass": True,
                "message_keywords_pass": True,
                "trace_error_pass": True,
                "trace_tool_pass": True,
                "structured_error_pass": True,
                "permission_bypass_pass": False,
            },
        },
    ]

    summary = summarize_results(results)

    assert summary.total_cases == 2
    assert summary.pass_rate == 0.5
    assert summary.failure_classification_accuracy == 1.0
    assert summary.fallback_decision_accuracy == 0.5
    assert summary.permission_bypass_rate == 1.0
