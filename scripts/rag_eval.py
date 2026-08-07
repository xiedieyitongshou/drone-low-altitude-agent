from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_CASES_PATH = PROJECT_ROOT / "evals" / "rag" / "cases.json"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "evals" / "reports"
DEFAULT_RETRIEVERS = ["tfidf", "bm25", "embedding", "hybrid"]


@dataclass(frozen=True)
class RagRetrieverSummary:
    total_cases: int
    pass_rate: float
    recall_at_k: float
    hit_rate_at_k: float
    mrr: float
    knowledge_type_accuracy: float
    chunk_type_accuracy: float
    metadata_filter_pass_rate: float
    permission_leakage_rate: float | None
    fallback_pass_rate: float | None
    query_rewrite_pass_rate: float | None
    retriever_source_coverage: float | None
    metadata_fields_pass_rate: float | None
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    max_latency_ms: float
    category_pass_rate: dict[str, float]


def run_eval(
    cases_path: Path = DEFAULT_CASES_PATH,
    *,
    retriever_names: list[str] | None = None,
) -> tuple[dict[str, RagRetrieverSummary], list[dict[str, Any]]]:
    cases = json.loads(cases_path.read_text(encoding="utf-8-sig"))
    selected_retrievers = retriever_names or DEFAULT_RETRIEVERS
    results: list[dict[str, Any]] = []
    summaries: dict[str, RagRetrieverSummary] = {}
    for retriever_name in selected_retrievers:
        retriever = build_eval_retriever(retriever_name)
        retriever_results = [run_rag_case(case, retriever_name=retriever_name, retriever=retriever) for case in cases]
        results.extend(retriever_results)
        summaries[retriever_name] = summarize_results(retriever_results)
    return summaries, results


def run_rag_case(case: dict[str, Any], *, retriever_name: str, retriever: Any) -> dict[str, Any]:
    from app.schemas.advice import KnowledgeAccessContext
    from app.services.advice_retriever import retrieve_knowledge_by_request

    request = build_request(case)
    access_context = KnowledgeAccessContext.model_validate(case.get("access_context") or {})
    start = perf_counter()
    response = retrieve_knowledge_by_request(request, access_context=access_context, retriever=retriever)
    latency_ms = round((perf_counter() - start) * 1000, 3)
    actual = extract_actual(response)
    checks = evaluate_rag_checks(case, actual)
    return {
        "case_id": case.get("id"),
        "category": case.get("category"),
        "retriever": retriever_name,
        "passed": checks["passed"],
        "checks": checks,
        "latency_ms": latency_ms,
        "expected": {
            "expected_knowledge_ids": case.get("expected_knowledge_ids") or [],
            "expected_excluded_knowledge_ids": case.get("expected_excluded_knowledge_ids") or [],
            "expected_knowledge_types": case.get("expected_knowledge_types") or [],
            "expected_chunk_types": case.get("expected_chunk_types") or [],
            "expected_behavior": case.get("expected_behavior") or {},
        },
        "actual": actual,
    }


def build_request(case: dict[str, Any]) -> Any:
    from app.schemas.advice import KnowledgeRetrievalRequest

    business_context = case.get("business_context") or {}
    risk_reasons = [str(case.get("query") or "")]
    risk_reasons.extend(str(item) for item in business_context.get("risk_tags") or [])
    return KnowledgeRetrievalRequest(
        task_type=business_context.get("task_type") or "cruise",
        risk_reasons=[item for item in risk_reasons if item],
        region=business_context.get("region"),
        province=business_context.get("province"),
        city=business_context.get("city"),
        top_k=int(case.get("top_k") or 5),
    )


def extract_actual(response: Any) -> dict[str, Any]:
    snippets = list(response.snippets)
    metadata_list = [snippet.metadata for snippet in snippets]
    return {
        "retrieval_status": response.retrieval_status,
        "retrieval_message": response.retrieval_message,
        "retrieval_metadata": response.retrieval_metadata,
        "knowledge_ids": [_knowledge_id(snippet) for snippet in snippets],
        "knowledge_types": [_metadata_value(metadata, "knowledge_type") for metadata in metadata_list],
        "chunk_types": [_metadata_value(metadata, "chunk_type") for metadata in metadata_list],
        "retrievers": [_metadata_value(metadata, "retriever") for metadata in metadata_list],
        "metadata_keys": sorted({key for metadata in metadata_list for key in metadata.keys()}),
        "metadata_list": metadata_list,
        "scores": [snippet.score for snippet in snippets],
        "snippet_count": len(snippets),
    }


def evaluate_rag_checks(case: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    expected_ids = [str(item) for item in case.get("expected_knowledge_ids") or []]
    excluded_ids = [str(item) for item in case.get("expected_excluded_knowledge_ids") or []]
    expected_types = [str(item) for item in case.get("expected_knowledge_types") or []]
    expected_chunk_types = [str(item) for item in case.get("expected_chunk_types") or []]
    expected_retrievers = [str(item) for item in case.get("expected_retrievers") or []]
    expected_metadata_fields = [str(item) for item in case.get("expected_metadata_fields") or []]
    expected_behavior = case.get("expected_behavior") or {}

    actual_ids = [str(item) for item in actual["knowledge_ids"]]
    matched_ids = [expected_id for expected_id in expected_ids if _id_matched(expected_id, actual_ids)]
    excluded_leaks = [excluded_id for excluded_id in excluded_ids if _id_matched(excluded_id, actual_ids)]
    first_rank = _first_relevant_rank(expected_ids, actual_ids)

    recall_denominator = len(expected_ids)
    recall_value = len(matched_ids) / recall_denominator if recall_denominator else None
    hit_value = bool(matched_ids) if expected_ids else None
    mrr_value = 1 / first_rank if first_rank else 0.0 if expected_ids else None

    knowledge_type_pass = _expected_values_present(expected_types, actual["knowledge_types"])
    chunk_type_pass = _expected_values_present(expected_chunk_types, actual["chunk_types"])
    retriever_source_pass = _expected_retrievers_present(expected_retrievers, actual)
    metadata_fields_pass = all(field in actual["metadata_keys"] for field in expected_metadata_fields)

    metadata_filter_pass = not excluded_leaks
    expected_metadata = case.get("expected_metadata") or {}
    if expected_metadata:
        metadata_filter_pass = metadata_filter_pass and _metadata_expected_present(expected_metadata, actual["metadata_list"])

    fallback_pass = evaluate_fallback_behavior(expected_behavior, actual)
    query_rewrite_pass = evaluate_query_rewrite_behavior(expected_behavior, actual)
    low_confidence_safety_pass = evaluate_low_confidence_safety(expected_behavior, actual)

    checks = {
        "recall_pass": True if not expected_ids else len(matched_ids) == len(expected_ids),
        "hit_pass": True if hit_value is None else hit_value,
        "excluded_knowledge_pass": not excluded_leaks,
        "knowledge_type_pass": knowledge_type_pass,
        "chunk_type_pass": chunk_type_pass,
        "metadata_filter_pass": metadata_filter_pass,
        "fallback_behavior_pass": fallback_pass,
        "query_rewrite_pass": query_rewrite_pass,
        "low_confidence_safety_pass": low_confidence_safety_pass,
        "retriever_source_pass": retriever_source_pass,
        "metadata_fields_pass": metadata_fields_pass,
        "recall_value": recall_value,
        "hit_value": hit_value,
        "mrr_value": mrr_value,
        "matched_ids": matched_ids,
        "excluded_leaks": excluded_leaks,
    }
    checks["passed"] = all(
        checks[key]
        for key in [
            "recall_pass",
            "excluded_knowledge_pass",
            "knowledge_type_pass",
            "chunk_type_pass",
            "metadata_filter_pass",
            "fallback_behavior_pass",
            "query_rewrite_pass",
            "low_confidence_safety_pass",
            "retriever_source_pass",
            "metadata_fields_pass",
        ]
    )
    return checks


def evaluate_fallback_behavior(expected_behavior: dict[str, Any], actual: dict[str, Any]) -> bool:
    if not expected_behavior:
        return True
    final_status = expected_behavior.get("final_status")
    if isinstance(final_status, list):
        return actual["retrieval_status"] in final_status
    if isinstance(final_status, str):
        return actual["retrieval_status"] == final_status
    return True


def evaluate_query_rewrite_behavior(expected_behavior: dict[str, Any], actual: dict[str, Any]) -> bool:
    if expected_behavior.get("second_attempt") != "query_rewritten":
        return True
    metadata = actual["retrieval_metadata"] or {}
    return bool(metadata.get("query_rewritten")) and len(metadata.get("attempts") or []) >= 2


def evaluate_low_confidence_safety(expected_behavior: dict[str, Any], actual: dict[str, Any]) -> bool:
    if not expected_behavior.get("should_not_fabricate_policy"):
        return True
    if expected_behavior.get("should_return_snippets") is False and actual["snippet_count"] != 0:
        return False
    return actual["retrieval_status"] == "fallback"


def summarize_results(results: list[dict[str, Any]]) -> RagRetrieverSummary:
    recall_values = [result["checks"]["recall_value"] for result in results if result["checks"]["recall_value"] is not None]
    hit_values = [result["checks"]["hit_value"] for result in results if result["checks"]["hit_value"] is not None]
    mrr_values = [result["checks"]["mrr_value"] for result in results if result["checks"]["mrr_value"] is not None]
    permission_results = [result for result in results if result["category"] == "permission"]
    fallback_results = [result for result in results if result["category"] == "fallback"]
    rewrite_results = [
        result
        for result in results
        if (result["expected"].get("expected_behavior") or {}).get("second_attempt") == "query_rewritten"
    ]
    retriever_source_results = [
        result for result in results if result["checks"].get("retriever_source_pass") is not None
    ]
    metadata_fields_results = [
        result for result in results if (result["actual"].get("metadata_keys") and result["checks"].get("metadata_fields_pass") is not None)
    ]
    latencies = [float(result["latency_ms"]) for result in results]

    category_counts: dict[str, int] = defaultdict(int)
    category_passes: dict[str, int] = defaultdict(int)
    for result in results:
        category = str(result.get("category") or "unknown")
        category_counts[category] += 1
        if result["passed"]:
            category_passes[category] += 1

    return RagRetrieverSummary(
        total_cases=len(results),
        pass_rate=_case_ratio(results, "passed"),
        recall_at_k=round(sum(recall_values) / len(recall_values), 4) if recall_values else 0.0,
        hit_rate_at_k=round(sum(1 for value in hit_values if value) / len(hit_values), 4) if hit_values else 0.0,
        mrr=round(sum(mrr_values) / len(mrr_values), 4) if mrr_values else 0.0,
        knowledge_type_accuracy=_check_ratio_for_applicable(results, "knowledge_type_pass", "expected_knowledge_types"),
        chunk_type_accuracy=_check_ratio_for_applicable(results, "chunk_type_pass", "expected_chunk_types"),
        metadata_filter_pass_rate=_check_ratio(results, "metadata_filter_pass"),
        permission_leakage_rate=None
        if not permission_results
        else round(
            sum(1 for result in permission_results if result["checks"]["excluded_leaks"]) / len(permission_results),
            4,
        ),
        fallback_pass_rate=None if not fallback_results else _check_ratio(fallback_results, "fallback_behavior_pass"),
        query_rewrite_pass_rate=None if not rewrite_results else _check_ratio(rewrite_results, "query_rewrite_pass"),
        retriever_source_coverage=None if not retriever_source_results else _check_ratio(retriever_source_results, "retriever_source_pass"),
        metadata_fields_pass_rate=None if not metadata_fields_results else _check_ratio(metadata_fields_results, "metadata_fields_pass"),
        avg_latency_ms=round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
        p50_latency_ms=_percentile(latencies, 50),
        p95_latency_ms=_percentile(latencies, 95),
        max_latency_ms=max(latencies, default=0.0),
        category_pass_rate={
            category: _ratio(category_passes[category], count)
            for category, count in sorted(category_counts.items())
        },
    )


def write_reports(
    summaries: dict[str, RagRetrieverSummary],
    results: list[dict[str, Any]],
    report_dir: Path = DEFAULT_REPORT_DIR,
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary_by_retriever": {name: summary.__dict__ for name, summary in summaries.items()},
        "results": results,
    }
    (report_dir / "rag_eval.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (report_dir / "rag_eval.md").write_text(build_markdown_report(summaries, results), encoding="utf-8")


def build_markdown_report(summaries: dict[str, RagRetrieverSummary], results: list[dict[str, Any]]) -> str:
    lines = [
        "# RAG Eval Report",
        "",
        "## Retriever Summary",
        "",
        "| Retriever | Pass | Recall@K | Hit@K | MRR | Metadata Filter | Leakage | Fallback | Rewrite | P95 Latency |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, summary in summaries.items():
        lines.append(
            "| "
            + " | ".join(
                [
                    name,
                    _pct(summary.pass_rate),
                    _pct(summary.recall_at_k),
                    _pct(summary.hit_rate_at_k),
                    f"{summary.mrr:.4f}",
                    _pct(summary.metadata_filter_pass_rate),
                    _optional_pct(summary.permission_leakage_rate),
                    _optional_pct(summary.fallback_pass_rate),
                    _optional_pct(summary.query_rewrite_pass_rate),
                    f"{summary.p95_latency_ms:.3f}ms",
                ]
            )
            + " |"
        )

    failures = [result for result in results if not result["passed"]]
    lines.extend(["", "## Failures", ""])
    if not failures:
        lines.append("- None")
    for failure in failures:
        lines.extend(
            [
                f"- {failure['case_id']} ({failure['retriever']}, {failure['category']})",
                f"  Expected IDs: {failure['expected']['expected_knowledge_ids']}",
                f"  Actual IDs: {failure['actual']['knowledge_ids']}",
                f"  Retrieval status: {failure['actual']['retrieval_status']}",
                f"  Checks: {failure['checks']}",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def build_eval_retriever(name: str) -> Any:
    from app.services.bm25_knowledge_store import LocalBm25KnowledgeStore
    from app.services.embedding_knowledge_store import LocalEmbeddingKnowledgeStore
    from app.services.knowledge_retrievers import (
        Bm25KnowledgeRetriever,
        EmbeddingKnowledgeRetriever,
        HybridKnowledgeRetriever,
        TfidfKnowledgeRetriever,
    )
    from app.services.vector_knowledge_store import LocalVectorKnowledgeStore

    normalized = name.strip().lower()
    if normalized == "tfidf":
        return TfidfKnowledgeRetriever(store=LocalVectorKnowledgeStore())
    if normalized == "bm25":
        return Bm25KnowledgeRetriever(store=LocalBm25KnowledgeStore())
    if normalized == "embedding":
        return EmbeddingKnowledgeRetriever(store=LocalEmbeddingKnowledgeStore())
    if normalized == "hybrid":
        return HybridKnowledgeRetriever(
            bm25_store=LocalBm25KnowledgeStore(),
            embedding_store=LocalEmbeddingKnowledgeStore(min_score=0.0),
        )
    raise ValueError(f"unsupported retriever: {name}")


def _knowledge_id(snippet: Any) -> str:
    return str(snippet.metadata.get("knowledge_id") or snippet.id)


def _metadata_value(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    return None if value in (None, "") else str(value)


def _id_matched(expected_id: str, actual_ids: list[str]) -> bool:
    return any(actual_id == expected_id or actual_id.startswith(expected_id) or expected_id in actual_id for actual_id in actual_ids)


def _first_relevant_rank(expected_ids: list[str], actual_ids: list[str]) -> int | None:
    for index, actual_id in enumerate(actual_ids, start=1):
        if any(_id_matched(expected_id, [actual_id]) for expected_id in expected_ids):
            return index
    return None


def _expected_values_present(expected_values: list[str], actual_values: list[str | None]) -> bool:
    if not expected_values:
        return True
    actual_set = {value for value in actual_values if value}
    return set(expected_values).issubset(actual_set)


def _expected_retrievers_present(expected_retrievers: list[str], actual: dict[str, Any]) -> bool:
    if not expected_retrievers:
        return True
    actual_sources = set(value for value in actual["retrievers"] if value)
    for metadata in actual["metadata_list"]:
        retrievers = metadata.get("retrievers")
        if isinstance(retrievers, list):
            actual_sources.update(str(item) for item in retrievers)
    return set(expected_retrievers).issubset(actual_sources)


def _metadata_expected_present(expected_metadata: dict[str, Any], metadata_list: list[dict[str, object]]) -> bool:
    for metadata in metadata_list:
        if all(_metadata_matches(metadata.get(key), expected_value) for key, expected_value in expected_metadata.items()):
            return True
    return False


def _metadata_matches(actual_value: object, expected_value: object) -> bool:
    if isinstance(actual_value, list):
        return str(expected_value) in {str(item) for item in actual_value}
    return actual_value == expected_value


def _check_ratio(results: list[dict[str, Any]], check_name: str) -> float:
    return _ratio(sum(1 for result in results if result["checks"].get(check_name)), len(results))


def _check_ratio_for_applicable(results: list[dict[str, Any]], check_name: str, expected_key: str) -> float:
    applicable = [result for result in results if result["expected"].get(expected_key)]
    if not applicable:
        return 0.0
    return _check_ratio(applicable, check_name)


def _case_ratio(results: list[dict[str, Any]], field: str) -> float:
    return _ratio(sum(1 for result in results if result.get(field)), len(results))


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(round((percentile / 100) * (len(ordered) - 1)), len(ordered) - 1)
    return round(ordered[index], 3)


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _optional_pct(value: float | None) -> str:
    return "N/A" if value is None else _pct(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RAG Eval across retrievers.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--retrievers", default=",".join(DEFAULT_RETRIEVERS))
    args = parser.parse_args()

    retriever_names = [item.strip() for item in args.retrievers.split(",") if item.strip()]
    summaries, results = run_eval(args.cases, retriever_names=retriever_names)
    write_reports(summaries, results, args.report_dir)
    best = summaries.get("hybrid") or next(iter(summaries.values()))
    print(f"RAG Eval completed: {len(results)} runs, hybrid_or_first_recall={_pct(best.recall_at_k)}")
    print(f"Reports written to: {args.report_dir}")


if __name__ == "__main__":
    main()
