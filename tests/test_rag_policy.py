from app.agent import RagDecision, decide_rag_tool_policy, rag_policy_metadata


def test_rag_policy_uses_rag_for_knowledge_intent():
    policy = decide_rag_tool_policy(intent="knowledge", query="深圳无人机政策有什么要注意")

    assert policy.decision == RagDecision.USE_RAG
    assert policy.tool_name == "query_knowledge_snippets"
    assert policy.reason == "knowledge intent explicitly requires knowledge retrieval"


def test_rag_policy_skips_history_query():
    policy = decide_rag_tool_policy(intent="history", query="查一下我上次深圳任务")

    assert policy.decision == RagDecision.SKIP_RAG
    assert policy.tool_name is None
    assert "history query" in policy.reason


def test_rag_policy_skips_rule_explanation_first():
    policy = decide_rag_tool_policy(intent="explain", query="为什么判高风险")

    assert policy.decision == RagDecision.SKIP_RAG
    assert "deterministic rule source" in policy.reason


def test_rag_policy_can_use_keywords_for_unknown_intent():
    policy = decide_rag_tool_policy(intent="unknown", query="查一下无人机 SOP")

    assert policy.decision == RagDecision.USE_RAG
    assert policy.tool_name == "query_knowledge_snippets"


def test_rag_policy_metadata_is_trace_friendly():
    policy = decide_rag_tool_policy(intent="recommend", query="推荐深圳窗口")

    assert rag_policy_metadata(policy) == {
        "rag_decision": "skip_rag",
        "rag_reason": "recommendation should use weather and rule windows first; RAG is optional advice after business result",
        "rag_tool_name": None,
    }
