# RAG Eval Report

## Retriever Summary

| Retriever | Pass | Recall@K | Hit@K | MRR | Metadata Filter | Leakage | Fallback | Rewrite | P95 Latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| tfidf | 14.29% | 100.00% | 100.00% | 1.0000 | 100.00% | 0.00% | 0.00% | 0.00% | 3296.234ms |
| bm25 | 14.29% | 100.00% | 100.00% | 1.0000 | 100.00% | 0.00% | 0.00% | 0.00% | 438.653ms |
| embedding | 14.29% | 0.00% | 0.00% | 0.0000 | 85.71% | 0.00% | 0.00% | 0.00% | 276.846ms |
| hybrid | 42.86% | 100.00% | 100.00% | 1.0000 | 100.00% | 0.00% | 0.00% | 0.00% | 21.234ms |

## Failures

- rag_policy_shenzhen_001 (tfidf, policy_hint)
  Expected IDs: ['policy-shenzhen']
  Actual IDs: ['policy-shenzhen-airspace-check-001', 'policy-registration-activation-001', 'policy-national-regulation-check-001']
  Retrieval status: success
  Checks: {'recall_pass': True, 'hit_pass': True, 'excluded_knowledge_pass': True, 'knowledge_type_pass': True, 'chunk_type_pass': False, 'metadata_filter_pass': True, 'fallback_behavior_pass': True, 'query_rewrite_pass': True, 'low_confidence_safety_pass': True, 'retriever_source_pass': False, 'metadata_fields_pass': True, 'recall_value': 1.0, 'hit_value': True, 'mrr_value': 1.0, 'matched_ids': ['policy-shenzhen'], 'excluded_leaks': [], 'passed': False}
- rag_sop_high_wind_001 (tfidf, sop)
  Expected IDs: []
  Actual IDs: ['policy-shenzhen-airspace-check-001', 'advice-high-wind-reduce-risk-001', 'policy-registration-activation-001', 'advice-warning-orange-cancel-002', 'advice-warning-yellow-caution-001']
  Retrieval status: success
  Checks: {'recall_pass': True, 'hit_pass': True, 'excluded_knowledge_pass': True, 'knowledge_type_pass': False, 'chunk_type_pass': False, 'metadata_filter_pass': True, 'fallback_behavior_pass': True, 'query_rewrite_pass': True, 'low_confidence_safety_pass': True, 'retriever_source_pass': True, 'metadata_fields_pass': True, 'recall_value': None, 'hit_value': None, 'mrr_value': None, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
- rag_faq_general_001 (tfidf, faq)
  Expected IDs: []
  Actual IDs: ['advice-thunderstorm-delay-001', 'advice-rainfall-delay-001', 'advice-recommend-window-001', 'advice-high-wind-reduce-risk-001', 'advice-warning-yellow-caution-001']
  Retrieval status: success
  Checks: {'recall_pass': True, 'hit_pass': True, 'excluded_knowledge_pass': True, 'knowledge_type_pass': False, 'chunk_type_pass': False, 'metadata_filter_pass': True, 'fallback_behavior_pass': True, 'query_rewrite_pass': True, 'low_confidence_safety_pass': True, 'retriever_source_pass': True, 'metadata_fields_pass': True, 'recall_value': None, 'hit_value': None, 'mrr_value': None, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
- rag_city_metadata_boost_001 (tfidf, hybrid_rerank)
  Expected IDs: []
  Actual IDs: ['policy-shenzhen-airspace-check-001', 'advice-high-wind-reduce-risk-001', 'advice-recommend-window-001', 'advice-warning-orange-cancel-002', 'advice-warning-yellow-caution-001']
  Retrieval status: success
  Checks: {'recall_pass': True, 'hit_pass': True, 'excluded_knowledge_pass': True, 'knowledge_type_pass': True, 'chunk_type_pass': True, 'metadata_filter_pass': True, 'fallback_behavior_pass': True, 'query_rewrite_pass': True, 'low_confidence_safety_pass': True, 'retriever_source_pass': True, 'metadata_fields_pass': False, 'recall_value': None, 'hit_value': None, 'mrr_value': None, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
- rag_query_rewrite_empty_001 (tfidf, fallback)
  Expected IDs: []
  Actual IDs: ['policy-shenzhen-airspace-check-001', 'advice-thunderstorm-delay-001', 'advice-rainfall-delay-001']
  Retrieval status: success
  Checks: {'recall_pass': True, 'hit_pass': True, 'excluded_knowledge_pass': True, 'knowledge_type_pass': True, 'chunk_type_pass': True, 'metadata_filter_pass': True, 'fallback_behavior_pass': False, 'query_rewrite_pass': False, 'low_confidence_safety_pass': True, 'retriever_source_pass': True, 'metadata_fields_pass': False, 'recall_value': None, 'hit_value': None, 'mrr_value': None, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
- rag_low_confidence_fallback_001 (tfidf, fallback)
  Expected IDs: []
  Actual IDs: ['policy-shenzhen-airspace-check-001', 'advice-thunderstorm-delay-001', 'advice-rainfall-delay-001']
  Retrieval status: success
  Checks: {'recall_pass': True, 'hit_pass': True, 'excluded_knowledge_pass': True, 'knowledge_type_pass': True, 'chunk_type_pass': True, 'metadata_filter_pass': True, 'fallback_behavior_pass': False, 'query_rewrite_pass': True, 'low_confidence_safety_pass': False, 'retriever_source_pass': True, 'metadata_fields_pass': True, 'recall_value': None, 'hit_value': None, 'mrr_value': None, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
- rag_policy_shenzhen_001 (bm25, policy_hint)
  Expected IDs: ['policy-shenzhen']
  Actual IDs: ['policy-shenzhen-airspace-check-001', 'policy-registration-activation-001', 'policy-national-regulation-check-001']
  Retrieval status: success
  Checks: {'recall_pass': True, 'hit_pass': True, 'excluded_knowledge_pass': True, 'knowledge_type_pass': True, 'chunk_type_pass': True, 'metadata_filter_pass': True, 'fallback_behavior_pass': True, 'query_rewrite_pass': True, 'low_confidence_safety_pass': True, 'retriever_source_pass': False, 'metadata_fields_pass': True, 'recall_value': 1.0, 'hit_value': True, 'mrr_value': 1.0, 'matched_ids': ['policy-shenzhen'], 'excluded_leaks': [], 'passed': False}
- rag_sop_high_wind_001 (bm25, sop)
  Expected IDs: []
  Actual IDs: ['policy-shenzhen-airspace-check-001', 'policy-national-regulation-check-001', 'policy-registration-activation-001', 'advice-warning-yellow-caution-001', 'advice-warning-orange-cancel-002']
  Retrieval status: success
  Checks: {'recall_pass': True, 'hit_pass': True, 'excluded_knowledge_pass': True, 'knowledge_type_pass': False, 'chunk_type_pass': False, 'metadata_filter_pass': True, 'fallback_behavior_pass': True, 'query_rewrite_pass': True, 'low_confidence_safety_pass': True, 'retriever_source_pass': True, 'metadata_fields_pass': True, 'recall_value': None, 'hit_value': None, 'mrr_value': None, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
- rag_faq_general_001 (bm25, faq)
  Expected IDs: []
  Actual IDs: ['advice-warning-yellow-caution-001', 'policy-shenzhen-airspace-check-001', 'policy-national-regulation-check-001', 'advice-warning-orange-cancel-002', 'policy-guangzhou-controlled-airspace-001']
  Retrieval status: success
  Checks: {'recall_pass': True, 'hit_pass': True, 'excluded_knowledge_pass': True, 'knowledge_type_pass': False, 'chunk_type_pass': False, 'metadata_filter_pass': True, 'fallback_behavior_pass': True, 'query_rewrite_pass': True, 'low_confidence_safety_pass': True, 'retriever_source_pass': True, 'metadata_fields_pass': True, 'recall_value': None, 'hit_value': None, 'mrr_value': None, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
- rag_city_metadata_boost_001 (bm25, hybrid_rerank)
  Expected IDs: []
  Actual IDs: ['policy-shenzhen-airspace-check-001', 'advice-warning-yellow-caution-001', 'advice-warning-orange-cancel-002', 'policy-national-regulation-check-001', 'advice-high-wind-reduce-risk-001']
  Retrieval status: success
  Checks: {'recall_pass': True, 'hit_pass': True, 'excluded_knowledge_pass': True, 'knowledge_type_pass': True, 'chunk_type_pass': True, 'metadata_filter_pass': True, 'fallback_behavior_pass': True, 'query_rewrite_pass': True, 'low_confidence_safety_pass': True, 'retriever_source_pass': True, 'metadata_fields_pass': False, 'recall_value': None, 'hit_value': None, 'mrr_value': None, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
- rag_query_rewrite_empty_001 (bm25, fallback)
  Expected IDs: []
  Actual IDs: ['policy-shenzhen-airspace-check-001', 'advice-warning-yellow-caution-001', 'advice-warning-orange-cancel-002']
  Retrieval status: success
  Checks: {'recall_pass': True, 'hit_pass': True, 'excluded_knowledge_pass': True, 'knowledge_type_pass': True, 'chunk_type_pass': True, 'metadata_filter_pass': True, 'fallback_behavior_pass': False, 'query_rewrite_pass': False, 'low_confidence_safety_pass': True, 'retriever_source_pass': True, 'metadata_fields_pass': False, 'recall_value': None, 'hit_value': None, 'mrr_value': None, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
- rag_low_confidence_fallback_001 (bm25, fallback)
  Expected IDs: []
  Actual IDs: ['policy-shenzhen-airspace-check-001', 'policy-national-regulation-check-001', 'advice-warning-yellow-caution-001']
  Retrieval status: success
  Checks: {'recall_pass': True, 'hit_pass': True, 'excluded_knowledge_pass': True, 'knowledge_type_pass': True, 'chunk_type_pass': True, 'metadata_filter_pass': True, 'fallback_behavior_pass': False, 'query_rewrite_pass': True, 'low_confidence_safety_pass': False, 'retriever_source_pass': True, 'metadata_fields_pass': True, 'recall_value': None, 'hit_value': None, 'mrr_value': None, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
- rag_policy_shenzhen_001 (embedding, policy_hint)
  Expected IDs: ['policy-shenzhen']
  Actual IDs: ['advice-warning-yellow-caution-001', 'advice-warning-orange-cancel-002']
  Retrieval status: success
  Checks: {'recall_pass': False, 'hit_pass': False, 'excluded_knowledge_pass': True, 'knowledge_type_pass': True, 'chunk_type_pass': False, 'metadata_filter_pass': False, 'fallback_behavior_pass': True, 'query_rewrite_pass': True, 'low_confidence_safety_pass': True, 'retriever_source_pass': False, 'metadata_fields_pass': True, 'recall_value': 0.0, 'hit_value': False, 'mrr_value': 0.0, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
- rag_sop_high_wind_001 (embedding, sop)
  Expected IDs: []
  Actual IDs: ['advice-warning-yellow-caution-001']
  Retrieval status: success
  Checks: {'recall_pass': True, 'hit_pass': True, 'excluded_knowledge_pass': True, 'knowledge_type_pass': False, 'chunk_type_pass': False, 'metadata_filter_pass': True, 'fallback_behavior_pass': True, 'query_rewrite_pass': True, 'low_confidence_safety_pass': True, 'retriever_source_pass': True, 'metadata_fields_pass': True, 'recall_value': None, 'hit_value': None, 'mrr_value': None, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
- rag_faq_general_001 (embedding, faq)
  Expected IDs: []
  Actual IDs: ['policy-shenzhen-airspace-check-001', 'advice-warning-yellow-caution-001', 'advice-warning-orange-cancel-002', 'advice-thunderstorm-delay-001', 'policy-national-regulation-check-001']
  Retrieval status: rewritten_success
  Checks: {'recall_pass': True, 'hit_pass': True, 'excluded_knowledge_pass': True, 'knowledge_type_pass': False, 'chunk_type_pass': False, 'metadata_filter_pass': True, 'fallback_behavior_pass': True, 'query_rewrite_pass': True, 'low_confidence_safety_pass': True, 'retriever_source_pass': True, 'metadata_fields_pass': True, 'recall_value': None, 'hit_value': None, 'mrr_value': None, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
- rag_city_metadata_boost_001 (embedding, hybrid_rerank)
  Expected IDs: []
  Actual IDs: ['advice-warning-yellow-caution-001', 'policy-shenzhen-airspace-check-001', 'advice-warning-orange-cancel-002']
  Retrieval status: rewritten_success
  Checks: {'recall_pass': True, 'hit_pass': True, 'excluded_knowledge_pass': True, 'knowledge_type_pass': True, 'chunk_type_pass': True, 'metadata_filter_pass': True, 'fallback_behavior_pass': True, 'query_rewrite_pass': True, 'low_confidence_safety_pass': True, 'retriever_source_pass': True, 'metadata_fields_pass': False, 'recall_value': None, 'hit_value': None, 'mrr_value': None, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
- rag_query_rewrite_empty_001 (embedding, fallback)
  Expected IDs: []
  Actual IDs: ['advice-high-wind-reduce-risk-001', 'advice-warning-yellow-caution-001', 'advice-recommend-window-001']
  Retrieval status: success
  Checks: {'recall_pass': True, 'hit_pass': True, 'excluded_knowledge_pass': True, 'knowledge_type_pass': True, 'chunk_type_pass': True, 'metadata_filter_pass': True, 'fallback_behavior_pass': False, 'query_rewrite_pass': False, 'low_confidence_safety_pass': True, 'retriever_source_pass': True, 'metadata_fields_pass': False, 'recall_value': None, 'hit_value': None, 'mrr_value': None, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
- rag_low_confidence_fallback_001 (embedding, fallback)
  Expected IDs: []
  Actual IDs: ['advice-warning-orange-cancel-002']
  Retrieval status: success
  Checks: {'recall_pass': True, 'hit_pass': True, 'excluded_knowledge_pass': True, 'knowledge_type_pass': True, 'chunk_type_pass': True, 'metadata_filter_pass': True, 'fallback_behavior_pass': False, 'query_rewrite_pass': True, 'low_confidence_safety_pass': False, 'retriever_source_pass': True, 'metadata_fields_pass': True, 'recall_value': None, 'hit_value': None, 'mrr_value': None, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
- rag_sop_high_wind_001 (hybrid, sop)
  Expected IDs: []
  Actual IDs: ['policy-shenzhen-airspace-check-001', 'advice-warning-yellow-caution-001', 'advice-warning-orange-cancel-002', 'policy-national-regulation-check-001', 'policy-registration-activation-001']
  Retrieval status: success
  Checks: {'recall_pass': True, 'hit_pass': True, 'excluded_knowledge_pass': True, 'knowledge_type_pass': False, 'chunk_type_pass': False, 'metadata_filter_pass': True, 'fallback_behavior_pass': True, 'query_rewrite_pass': True, 'low_confidence_safety_pass': True, 'retriever_source_pass': True, 'metadata_fields_pass': True, 'recall_value': None, 'hit_value': None, 'mrr_value': None, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
- rag_faq_general_001 (hybrid, faq)
  Expected IDs: []
  Actual IDs: ['advice-warning-yellow-caution-001', 'policy-shenzhen-airspace-check-001', 'advice-warning-orange-cancel-002', 'policy-national-regulation-check-001', 'policy-guangzhou-controlled-airspace-001']
  Retrieval status: success
  Checks: {'recall_pass': True, 'hit_pass': True, 'excluded_knowledge_pass': True, 'knowledge_type_pass': False, 'chunk_type_pass': False, 'metadata_filter_pass': True, 'fallback_behavior_pass': True, 'query_rewrite_pass': True, 'low_confidence_safety_pass': True, 'retriever_source_pass': True, 'metadata_fields_pass': True, 'recall_value': None, 'hit_value': None, 'mrr_value': None, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
- rag_query_rewrite_empty_001 (hybrid, fallback)
  Expected IDs: []
  Actual IDs: ['policy-shenzhen-airspace-check-001', 'advice-warning-yellow-caution-001', 'advice-warning-orange-cancel-002']
  Retrieval status: success
  Checks: {'recall_pass': True, 'hit_pass': True, 'excluded_knowledge_pass': True, 'knowledge_type_pass': True, 'chunk_type_pass': True, 'metadata_filter_pass': True, 'fallback_behavior_pass': False, 'query_rewrite_pass': False, 'low_confidence_safety_pass': True, 'retriever_source_pass': True, 'metadata_fields_pass': False, 'recall_value': None, 'hit_value': None, 'mrr_value': None, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
- rag_low_confidence_fallback_001 (hybrid, fallback)
  Expected IDs: []
  Actual IDs: ['advice-warning-orange-cancel-002', 'advice-warning-yellow-caution-001', 'policy-national-regulation-check-001']
  Retrieval status: success
  Checks: {'recall_pass': True, 'hit_pass': True, 'excluded_knowledge_pass': True, 'knowledge_type_pass': True, 'chunk_type_pass': True, 'metadata_filter_pass': True, 'fallback_behavior_pass': False, 'query_rewrite_pass': True, 'low_confidence_safety_pass': False, 'retriever_source_pass': True, 'metadata_fields_pass': True, 'recall_value': None, 'hit_value': None, 'mrr_value': None, 'matched_ids': [], 'excluded_leaks': [], 'passed': False}
