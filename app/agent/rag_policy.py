from enum import StrEnum

from pydantic import BaseModel


class RagDecision(StrEnum):
    USE_RAG = "use_rag"
    SKIP_RAG = "skip_rag"


class RagToolPolicy(BaseModel):
    decision: RagDecision
    reason: str
    tool_name: str | None = None


RAG_REQUIRED_INTENTS = {"knowledge"}
RAG_SKIPPED_INTENT_REASONS = {
    "history": "history query only reads user conversation records",
    "evaluate": "risk evaluation should use rule engine first; RAG is optional advice after business result",
    "recommend": "recommendation should use weather and rule windows first; RAG is optional advice after business result",
    "compare": "comparison should use business comparison tool first; RAG is optional advice after business result",
    "explain": "rule explanation should use deterministic rule source first",
}
RAG_TRIGGER_KEYWORDS = {"政策", "SOP", "FAQ", "知识库", "操作建议", "注意事项", "规则", "规定", "风险说明"}


def decide_rag_tool_policy(*, intent: str | None, query: str | None = None) -> RagToolPolicy:
    normalized_intent = (intent or "").strip().lower()
    if normalized_intent in RAG_REQUIRED_INTENTS:
        return RagToolPolicy(
            decision=RagDecision.USE_RAG,
            reason="knowledge intent explicitly requires knowledge retrieval",
            tool_name="query_knowledge_snippets",
        )

    if normalized_intent in RAG_SKIPPED_INTENT_REASONS:
        return RagToolPolicy(
            decision=RagDecision.SKIP_RAG,
            reason=RAG_SKIPPED_INTENT_REASONS[normalized_intent],
        )

    if query and any(keyword.lower() in query.lower() for keyword in RAG_TRIGGER_KEYWORDS):
        return RagToolPolicy(
            decision=RagDecision.USE_RAG,
            reason="query contains explicit knowledge retrieval keywords",
            tool_name="query_knowledge_snippets",
        )

    return RagToolPolicy(
        decision=RagDecision.SKIP_RAG,
        reason="no knowledge retrieval trigger detected",
    )


def rag_policy_metadata(policy: RagToolPolicy) -> dict[str, str | None]:
    return {
        "rag_decision": policy.decision.value,
        "rag_reason": policy.reason,
        "rag_tool_name": policy.tool_name,
    }
