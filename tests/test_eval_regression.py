import pytest

from scripts.failure_recovery_eval import run_eval as run_failure_recovery_eval
from scripts.multi_turn_state_eval import run_eval as run_multi_turn_state_eval
from scripts.rag_eval import run_eval as run_rag_eval
from scripts.rag_eval import quality_gate_failures as rag_quality_gate_failures
from scripts.tool_calling_eval import run_eval as run_tool_calling_eval


def _require_cases(results, required, *, multi_turn=False):
    present = {row["case_id"] for row in results}
    assert set(required).issubset(present), f"missing baseline cases: {sorted(set(required) - present)}"
    identities = [(row["case_id"], row.get("turn_index")) if multi_turn else row["case_id"] for row in results]
    assert len(identities) == len(set(identities)), "duplicate case/turn identities"


@pytest.mark.eval_fast
def test_tool_calling_eval_fast_gate():
    summary, results = run_tool_calling_eval()

    _require_cases(results, {
        "agent_clarification_missing_location_001", "agent_permission_denied_001",
        "agent_modify_context_001", "agent_tool_failure_fallback_001",
    })

    assert summary.total_cases >= 9
    assert summary.pass_rate == 1.0, [result["case_id"] for result in results if not result["passed"]]
    assert summary.clarification_pass_rate == 1.0
    assert summary.clarification_continuation_pass_rate == 1.0
    assert summary.guardrail_pass_rate == 1.0
    assert summary.fallback_accuracy == 1.0
    for category in ("clarification", "permission", "modify", "tool_failure"):
        assert summary.category_pass_rate.get(category) == 1.0, category

    assert summary.intent_accuracy >= 0.95, f"intent_accuracy={summary.intent_accuracy:.4f}"
    assert summary.tool_selection_accuracy >= 0.90, (
        f"tool_selection_accuracy={summary.tool_selection_accuracy:.4f}"
    )
    assert summary.missing_tool_call_rate <= 0.05, (
        f"missing_tool_call_rate={summary.missing_tool_call_rate:.4f}"
    )
    assert summary.unexpected_tool_violation_rate == 0, (
        f"unexpected_tool_violation_rate={summary.unexpected_tool_violation_rate:.4f}"
    )


@pytest.mark.eval_fast
def test_multi_turn_state_eval_fast_gate():
    summary, results = run_multi_turn_state_eval()

    _require_cases(results, {
        "multi_turn_modify_location_001", "multi_turn_modify_time_001", "multi_turn_modify_task_type_001",
        "multi_turn_clarification_continue_001", "multi_turn_intent_switch_to_recommend_001",
        "multi_turn_context_pollution_001", "multi_turn_session_isolation_001",
    }, multi_turn=True)

    assert summary.total_dialogues > 0 and summary.total_turns > 0
    assert summary.pass_rate == 1.0, [result["case_id"] for result in results if not result["passed"]]
    assert summary.clarification_continuation_pass_rate == 1.0
    assert summary.modified_fields_accuracy == 1.0
    assert summary.invalidated_tools_accuracy == 1.0

    assert summary.state_inheritance_accuracy >= 0.95, (
        f"state_inheritance_accuracy={summary.state_inheritance_accuracy:.4f}"
    )
    assert summary.state_override_accuracy >= 0.95, (
        f"state_override_accuracy={summary.state_override_accuracy:.4f}"
    )
    assert summary.tool_input_consistency >= 0.95, (
        f"tool_input_consistency={summary.tool_input_consistency:.4f}"
    )
    assert summary.context_pollution_rate == 0, f"context_pollution_rate={summary.context_pollution_rate:.4f}"
    assert summary.session_isolation_pass_rate is not None, "session_isolation_pass_rate is None"
    assert summary.session_isolation_pass_rate >= 0.95, (
        f"session_isolation_pass_rate={summary.session_isolation_pass_rate:.4f}"
    )


@pytest.mark.eval_fast
def test_failure_recovery_eval_fast_gate():
    summary, results = run_failure_recovery_eval()

    _require_cases(results, {
        "failure_timeout_weather_001", "failure_external_dependency_001", "failure_invalid_tool_input_001",
        "failure_permission_denied_001", "failure_auth_required_001", "failure_not_found_history_001",
        "failure_internal_error_001",
    })

    assert summary.total_cases > 0
    assert summary.pass_rate == 1.0, [result["case_id"] for result in results if not result["passed"]]
    assert summary.no_fabrication_pass_rate == 1.0
    assert summary.structured_error_completeness == 1.0
    assert summary.retryability_accuracy == 1.0

    assert summary.failure_classification_accuracy >= 0.95, (
        f"failure_classification_accuracy={summary.failure_classification_accuracy:.4f}"
    )
    assert summary.recovery_action_accuracy >= 0.95, (
        f"recovery_action_accuracy={summary.recovery_action_accuracy:.4f}"
    )
    assert summary.fallback_decision_accuracy >= 0.95, (
        f"fallback_decision_accuracy={summary.fallback_decision_accuracy:.4f}"
    )
    assert summary.trace_error_coverage >= 0.95, f"trace_error_coverage={summary.trace_error_coverage:.4f}"
    assert summary.permission_bypass_rate == 0, f"permission_bypass_rate={summary.permission_bypass_rate:.4f}"


@pytest.mark.eval_fast
def test_rag_eval_hybrid_fast_gate():
    summaries, results = run_rag_eval(retriever_names=["hybrid"])
    _require_cases(results, {
        "rag_private_visibility_block_001", "rag_private_authorized_001",
        "rag_low_confidence_fallback_001", "rag_battery_life_no_answer_001",
    })
    summary = summaries["hybrid"]

    assert not rag_quality_gate_failures(summary)

    assert summary.recall_at_k >= 0.70, f"hybrid.recall_at_k={summary.recall_at_k:.4f}"
    assert summary.hit_rate_at_k >= 0.70, f"hybrid.hit_rate_at_k={summary.hit_rate_at_k:.4f}"
    assert summary.metadata_filter_pass_rate >= 0.95, (
        f"hybrid.metadata_filter_pass_rate={summary.metadata_filter_pass_rate:.4f}"
    )
    assert summary.permission_leakage_rate == 0, (
        f"hybrid.permission_leakage_rate={summary.permission_leakage_rate:.4f}"
    )
    assert summary.fallback_pass_rate == 1.0, f"hybrid.fallback_pass_rate={summary.fallback_pass_rate}"
    assert summary.p95_latency_ms <= 500, f"hybrid.p95_latency_ms={summary.p95_latency_ms:.3f}"


def test_multi_turn_gate_rejects_removed_clarification_case(monkeypatch, tmp_path):
    import json
    from scripts.multi_turn_state_eval import DEFAULT_CASES_PATH

    cases = json.loads(DEFAULT_CASES_PATH.read_text(encoding="utf-8-sig"))
    cases = [case for case in cases if case["category"] != "clarification_continuation"]
    source = tmp_path / "without-clarification.json"
    source.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
    summary, results = run_multi_turn_state_eval(source)
    assert summary.pass_rate == 1.0
    monkeypatch.setitem(globals(), "run_multi_turn_state_eval", lambda: (summary, results))
    with pytest.raises(AssertionError, match="missing baseline cases"):
        test_multi_turn_state_eval_fast_gate()
