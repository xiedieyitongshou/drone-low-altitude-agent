from scripts.rag_eval import evaluate_rag_checks, summarize_results


def test_evaluate_rag_checks_passes_expected_id_and_metadata():
    case = {
        "id": "case-1",
        "category": "policy_hint",
        "expected_knowledge_ids": ["policy-shenzhen"],
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
        "expected_excluded_knowledge_ids": ["private-user-b"],
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
    assert checks["excluded_leaks"] == ["private-user-b"]


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
