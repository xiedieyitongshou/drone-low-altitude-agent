import pytest

from scripts.failure_recovery_eval import run_eval as run_failure_recovery_eval
from scripts.multi_turn_state_eval import run_eval as run_multi_turn_state_eval
from scripts.rag_eval import run_eval as run_rag_eval
from scripts.tool_calling_eval import run_eval as run_tool_calling_eval


@pytest.mark.eval_fast
def test_tool_calling_eval_fast_gate():
    summary, _ = run_tool_calling_eval()

    assert summary.intent_accuracy >= 0.95, f"intent_accuracy={summary.intent_accuracy:.4f}"
    assert summary.tool_selection_accuracy >= 0.90, (
        f"tool_selection_accuracy={summary.tool_selection_accuracy:.4f}"
    )
    assert summary.missing_tool_call_rate <= 0.05, (
        f"missing_tool_call_rate={summary.missing_tool_call_rate:.4f}"
    )
    assert summary.unexpected_tool_violation_rate <= 0.10, (
        f"unexpected_tool_violation_rate={summary.unexpected_tool_violation_rate:.4f}"
    )


@pytest.mark.eval_fast
def test_multi_turn_state_eval_fast_gate():
    summary, _ = run_multi_turn_state_eval()

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
    summary, _ = run_failure_recovery_eval()

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
    summaries, _ = run_rag_eval(retriever_names=["hybrid"])
    summary = summaries["hybrid"]

    assert summary.recall_at_k >= 0.70, f"hybrid.recall_at_k={summary.recall_at_k:.4f}"
    assert summary.hit_rate_at_k >= 0.70, f"hybrid.hit_rate_at_k={summary.hit_rate_at_k:.4f}"
    assert summary.metadata_filter_pass_rate >= 0.95, (
        f"hybrid.metadata_filter_pass_rate={summary.metadata_filter_pass_rate:.4f}"
    )
    assert summary.permission_leakage_rate == 0, (
        f"hybrid.permission_leakage_rate={summary.permission_leakage_rate:.4f}"
    )
    assert summary.p95_latency_ms <= 500, f"hybrid.p95_latency_ms={summary.p95_latency_ms:.3f}"
