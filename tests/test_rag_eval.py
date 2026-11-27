from scripts.rag_eval import _id_matched, evaluate_rag_checks, run_eval, summarize_results
from scripts.rag_eval import DEFAULT_CASES_PATH, quality_gate_failures
from copy import deepcopy
import json
import pytest


@pytest.mark.parametrize("case_id,mutation,failed_gate", [
    ("rag_low_confidence_fallback_001", "fallback_snippet", "fallback_cases_passed"),
    ("rag_private_authorized_001", "missing_authorized_result", "permission_cases_passed"),
])
def test_critical_rag_case_cannot_be_hidden_by_aggregate_metrics(case_id, mutation, failed_gate):
    _, results = run_eval(retriever_names=["hybrid"])
    row = next(result for result in results if result["case_id"] == case_id)
    case = next(case for case in json.loads(DEFAULT_CASES_PATH.read_text(encoding="utf-8-sig")) if case["id"] == case_id)
    actual = deepcopy(row["actual"])
    if mutation == "fallback_snippet":
        actual["snippet_count"] = 1
    else:
        actual["knowledge_ids"] = []
    row["checks"] = evaluate_rag_checks(case, actual)
    row["actual"] = actual
    row["passed"] = row["checks"]["passed"]
    summary = summarize_results(results)
    assert summary.fallback_pass_rate == 1.0
    assert summary.permission_leakage_rate == 0
    assert row["passed"] is False
    assert failed_gate in quality_gate_failures(summary)


def test_default_bm25_passes_applicability_permission_and_no_answer_cases(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "false")
    summaries, results = run_eval(retriever_names=["bm25"])
    assert summaries["bm25"].pass_rate == 1.0, [result["case_id"] for result in results if not result["passed"]]
    assert summaries["bm25"].fallback_pass_rate == 1.0


def test_knowledge_id_matching_is_exact():
    assert _id_matched("policy-shenzhen", ["policy-shenzhen-airspace-check-001"]) is False


def test_evaluate_rag_checks_passes_expected_id_and_metadata():
    case = {
        "id": "case-1",
        "category": "policy_hint",
        "expected_knowledge_ids": ["policy-shenzhen-airspace-check-001"],
        "expected_metadata": {"city": "深圳", "visibility": "public"},
    }
    actual = {
        "retrieval_status": "success",
        "retrieval_metadata": {},
        "knowledge_ids": ["policy-shenzhen-airspace-check-001"],
        "knowledge_types": ["policy_hint"],
        "chunk_types": ["policy_clause"],
        "retrievers": ["bm25"],
        "metadata_keys": ["city", "visibility", "knowledge_id"],
        "metadata_list": [{"city": "深圳", "visibility": "public", "knowledge_id": "policy-shenzhen-airspace-check-001"}],
        "snippet_count": 1,
    }

    checks = evaluate_rag_checks(case, actual)

    assert checks["passed"] is True
    assert checks["recall_value"] == 1.0
    assert checks["hit_value"] is True


def test_evaluate_rag_checks_detects_permission_leakage():
    case = {
        "id": "case-1",
        "category": "permission",
        "expected_excluded_knowledge_ids": ["private-user-b-secret"],
    }
    actual = {
        "retrieval_status": "success",
        "retrieval_metadata": {},
        "knowledge_ids": ["private-user-b-secret"],
        "knowledge_types": [],
        "chunk_types": [],
        "retrievers": ["bm25"],
        "metadata_keys": [],
        "metadata_list": [],
        "snippet_count": 1,
    }

    checks = evaluate_rag_checks(case, actual)

    assert checks["passed"] is False
    assert checks["excluded_knowledge_pass"] is False
    assert checks["excluded_leaks"] == ["private-user-b-secret"]


def test_summarize_results_computes_recall_and_latency():
    results = [
        {
            "passed": True,
            "category": "policy_hint",
            "latency_ms": 10.0,
            "expected": {"expected_knowledge_types": ["policy_hint"], "expected_chunk_types": ["policy_clause"]},
            "actual": {},
            "checks": {
                "recall_value": 1.0,
                "hit_value": True,
                "mrr_value": 1.0,
                "knowledge_type_pass": True,
                "chunk_type_pass": True,
                "metadata_filter_pass": True,
                "retriever_source_pass": True,
                "metadata_fields_pass": True,
            },
        },
        {
            "passed": False,
            "category": "permission",
            "latency_ms": 30.0,
            "expected": {},
            "actual": {},
            "checks": {
                "recall_value": None,
                "hit_value": None,
                "mrr_value": None,
                "knowledge_type_pass": True,
                "chunk_type_pass": True,
                "metadata_filter_pass": False,
                "retriever_source_pass": True,
                "metadata_fields_pass": True,
                "excluded_leaks": ["private-user-b"],
            },
        },
    ]

    summary = summarize_results(results)

    assert summary.total_cases == 2
    assert summary.pass_rate == 0.5
    assert summary.recall_at_k == 1.0
    assert summary.hit_rate_at_k == 1.0
    assert summary.permission_leakage_rate == 1.0
    assert summary.avg_latency_ms == 20.0
