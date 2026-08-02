from app.schemas.composed_response import UnifiedBusinessResponse
from app.services import response_explainer
from app.services.response_explainer import explain_business_response


def test_explainer_skips_llm_when_policy_sensitive_response_lacks_evidence(monkeypatch):
    llm_calls = []
    monkeypatch.setattr(response_explainer, "generate_text", lambda **kwargs: llm_calls.append(kwargs) or "LLM 文本")
    response = UnifiedBusinessResponse(
        scene="evaluate",
        summary="深圳任务涉及禁飞区审批。",
        overall_decision="谨慎飞行",
        allow_execute=False,
        risk_reasons=["涉及审批"],
        details={},
    )

    result = explain_business_response(response)

    assert result.source == "template"
    assert result.llm_used is False
    assert llm_calls == []
    assert result.guardrail_results[0].error_code == "MISSING_POLICY_EVIDENCE_FOR_LLM"
    assert "不能替代官方审批" in result.text


def test_explainer_discards_unsafe_llm_output_and_falls_back_to_template(monkeypatch):
    monkeypatch.setattr(response_explainer, "generate_text", lambda **kwargs: "本次任务绝对安全，无需审批。")
    response = UnifiedBusinessResponse(
        scene="evaluate",
        summary="深圳任务结论为谨慎飞行。",
        overall_decision="谨慎飞行",
        allow_execute=False,
        risk_reasons=["风速较大"],
        details={"knowledge_snippets": [{"id": "k1", "content": "示例知识"}]},
    )

    result = explain_business_response(response)

    assert result.source == "template"
    assert result.llm_used is False
    assert result.guardrail_results[-1].error_code == "UNSAFE_FINAL_RESPONSE"
    assert "绝对安全" not in result.text
    assert "不能替代官方审批" in result.text


def test_explainer_keeps_safe_llm_output_when_guardrail_passes(monkeypatch):
    monkeypatch.setattr(response_explainer, "generate_text", lambda **kwargs: "本次任务建议谨慎执行，需关注天气和现场限制。")
    response = UnifiedBusinessResponse(
        scene="recommend",
        summary="广州任务推荐窗口已生成。",
        overall_decision="谨慎飞行",
        allow_execute=True,
        risk_reasons=["阵风"],
        details={"knowledge_snippets": [{"id": "k1", "content": "示例知识"}]},
    )

    result = explain_business_response(response)

    assert result.source == "llm"
    assert result.llm_used is True
    assert result.text == "本次任务建议谨慎执行，需关注天气和现场限制。"
    assert [item.allowed for item in result.guardrail_results] == [True, True]
