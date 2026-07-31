import logging

from app.agent import (
    ToolExecutionContext,
    ToolExecutor,
    ToolRegistry,
    ToolSpec,
    build_agent_log_context,
    initialize_state,
    summarize_for_log,
)


def test_build_agent_log_context_uses_minimal_fields_by_default(monkeypatch):
    monkeypatch.delenv("AGENT_LOG_RAW_PAYLOAD", raising=False)
    state = initialize_state("深圳明天下午适合飞吗", user_id="user-1", session_id="session-1")

    context = build_agent_log_context(
        event="tool_call",
        state=state,
        tool_name="retrieve_rag_advice",
        raw_payload={
            "query": "深圳明天下午适合飞吗",
            "authorization": "Bearer secret-token",
            "long_text": "a" * 120,
        },
    )

    assert context["trace_id"] == state.trace_id
    assert context["run_id"] == state.run_id
    assert context["user_id"] == "user-1"
    assert context["session_id"] == "session-1"
    assert context["tool_name"] == "retrieve_rag_advice"
    assert context["payload"]["authorization"] == "[REDACTED]"
    assert context["payload"]["query"] == "深圳明天下午适合飞吗"
    assert context["payload"]["long_text"] == f"{'a' * 80}..."


def test_build_agent_log_context_respects_raw_payload_debug_but_keeps_sensitive_redaction(monkeypatch):
    monkeypatch.setenv("AGENT_LOG_RAW_PAYLOAD", "true")
    state = initialize_state("debug", user_id="user-1")

    context = build_agent_log_context(
        event="tool_result",
        state=state,
        raw_payload={
            "password": "secret-password",
            "long_text": "a" * 120,
        },
    )

    assert context["payload"]["password"] == "[REDACTED]"
    assert context["payload"]["long_text"] == "a" * 120


def test_summarize_for_log_summarizes_plain_text():
    summary = summarize_for_log("a" * 100)

    assert summary == {"text_preview": f"{'a' * 80}...", "text_length": 100}


def test_tool_executor_emits_sanitized_structured_logs(caplog, monkeypatch):
    monkeypatch.delenv("AGENT_LOG_RAW_PAYLOAD", raising=False)
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="retrieve_rag_advice",
            description="Fake RAG tool.",
            side_effect="read_only",
            risk_level="medium",
        ),
        lambda payload, context: {"matched_count": 1, "authorization": payload["authorization"]},
    )
    executor = ToolExecutor(tool_registry=registry, trace_recorder=None)
    state = initialize_state("查政策", user_id="user-1")

    with caplog.at_level(logging.INFO, logger="drone-low-altitude-agent.agent"):
        result = executor.execute(
            tool_name="retrieve_rag_advice",
            tool_input={"task_type": "inspection", "authorization": "Bearer secret-token"},
            state=state,
            context=ToolExecutionContext(user_id="user-1"),
        )

    assert result.success is True
    records = [record for record in caplog.records if record.name == "drone-low-altitude-agent.agent"]
    assert [record.event for record in records] == ["tool_call", "tool_result"]
    assert records[0].trace_id == state.trace_id
    assert records[0].tool_name == "retrieve_rag_advice"
    assert records[0].payload["authorization"] == "[REDACTED]"
    assert records[1].payload["data"]["authorization"] == "[REDACTED]"
