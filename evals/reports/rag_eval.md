# RAG Eval Report

## Retriever Summary

| Retriever | Pass | Recall@K | Hit@K | MRR | Metadata Filter | Leakage | Fallback | Rewrite | P95 Latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| tfidf | 77.78% | 60.00% | 60.00% | 0.6000 | 100.00% | 0.00% | 100.00% | N/A | 17.685ms |
| bm25 | 100.00% | 100.00% | 100.00% | 1.0000 | 100.00% | 0.00% | 100.00% | N/A | 11.409ms |
| embedding | 80.00% | 66.67% | 66.67% | 0.6667 | 100.00% | 0.00% | 100.00% | N/A | 15.748ms |
| hybrid | 100.00% | 100.00% | 100.00% | 0.9286 | 100.00% | 0.00% | 100.00% | N/A | 26.040ms |

## Failures

- rag_wind_survey_001 (tfidf, sop)
  Expected IDs: ['advice-high-wind-change-task-002']
  Actual IDs: []
  Retrieval status: fallback
  Checks: {'recall_pass': False, 'hit_pass': False, 'excluded_knowledge_pass': True, 'knowledge_type_pass': False, 'chunk_type_pass': True, 'metadata_filter_pass': True, 'fallback_behavior_pass': True, 'query_rewrite_pass': True, 'low_confidence_safety_pass': True, 'retriever_source_pass': True, 'metadata_fields_pass': True, 'recall_value': 0.0, 'hit_value': False, 'mrr_value': 0.0, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
- rag_warning_topic_001 (tfidf, applicability)
  Expected IDs: ['advice-warning-yellow-caution-001']
  Actual IDs: []
  Retrieval status: fallback
  Checks: {'recall_pass': False, 'hit_pass': False, 'excluded_knowledge_pass': True, 'knowledge_type_pass': False, 'chunk_type_pass': True, 'metadata_filter_pass': True, 'fallback_behavior_pass': True, 'query_rewrite_pass': True, 'low_confidence_safety_pass': True, 'retriever_source_pass': True, 'metadata_fields_pass': True, 'recall_value': 0.0, 'hit_value': False, 'mrr_value': 0.0, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
- rag_policy_shenzhen_001 (embedding, policy_hint)
  Expected IDs: ['policy-shenzhen-airspace-check-001']
  Actual IDs: []
  Retrieval status: fallback
  Checks: {'recall_pass': False, 'hit_pass': False, 'excluded_knowledge_pass': True, 'knowledge_type_pass': False, 'chunk_type_pass': True, 'metadata_filter_pass': True, 'fallback_behavior_pass': True, 'query_rewrite_pass': True, 'low_confidence_safety_pass': True, 'retriever_source_pass': True, 'metadata_fields_pass': True, 'recall_value': 0.0, 'hit_value': False, 'mrr_value': 0.0, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
- rag_wind_survey_001 (embedding, sop)
  Expected IDs: ['advice-high-wind-change-task-002']
  Actual IDs: []
  Retrieval status: fallback
  Checks: {'recall_pass': False, 'hit_pass': False, 'excluded_knowledge_pass': True, 'knowledge_type_pass': False, 'chunk_type_pass': True, 'metadata_filter_pass': True, 'fallback_behavior_pass': True, 'query_rewrite_pass': True, 'low_confidence_safety_pass': True, 'retriever_source_pass': True, 'metadata_fields_pass': True, 'recall_value': 0.0, 'hit_value': False, 'mrr_value': 0.0, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
