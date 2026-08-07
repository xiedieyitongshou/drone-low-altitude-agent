from scripts.failure_recovery_eval import evaluate_failure_checks, summarize_results


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
