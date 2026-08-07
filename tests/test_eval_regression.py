import pytest

from scripts.failure_recovery_eval import run_eval as run_failure_recovery_eval
from scripts.multi_turn_state_eval import run_eval as run_multi_turn_state_eval
from scripts.rag_eval import run_eval as run_rag_eval
from scripts.tool_calling_eval import run_eval as run_tool_calling_eval


@pytest.mark.eval_fast
def test_tool_calling_eval_fast_gate():
    summary, _ = run_tool_calling_eval()

    assert summary.intent_accuracy >= 0.95
    assert summary.tool_selection_accuracy >= 0.90
    assert summary.missing_tool_call_rate <= 0.05
    assert summary.unexpected_tool_violation_rate <= 0.10


@pytest.mark.eval_fast
def test_multi_turn_state_eval_fast_gate():
    summary, _ = run_multi_turn_state_eval()

    assert summary.state_inheritance_accuracy >= 0.95
    assert summary.state_override_accuracy >= 0.95
    assert summary.tool_input_consistency >= 0.95
    assert summary.context_pollution_rate == 0
    assert summary.session_isolation_pass_rate is not None
    assert summary.session_isolation_pass_rate >= 0.95


@pytest.mark.eval_fast
def test_failure_recovery_eval_fast_gate():
    summary, _ = run_failure_recovery_eval()

    assert summary.failure_classification_accuracy >= 0.95
    assert summary.recovery_action_accuracy >= 0.95
    assert summary.fallback_decision_accuracy >= 0.95
    assert summary.trace_error_coverage >= 0.95
    assert summary.permission_bypass_rate == 0


@pytest.mark.eval_fast
def test_rag_eval_hybrid_fast_gate():
    summaries, _ = run_rag_eval(retriever_names=["hybrid"])
    summary = summaries["hybrid"]

    assert summary.recall_at_k >= 0.70
    assert summary.hit_rate_at_k >= 0.70
    assert summary.metadata_filter_pass_rate >= 0.95
    assert summary.permission_leakage_rate == 0
    assert summary.p95_latency_ms <= 500
