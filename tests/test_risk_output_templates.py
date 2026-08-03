from app.schemas.composed_response import (
    ComposedRecommendationWindow,
    UnifiedBusinessResponse,
)
from app.services.risk_output_templates import (
    OFFICIAL_BOUNDARY_NOTE,
    find_unsafe_output_keywords,
    render_business_response_template,
    template_kind,
)


def test_prohibited_output_template_snapshot():
    response = UnifiedBusinessResponse(
        scene="evaluate",
        summary="深圳任务涉及禁飞区审批。",
        overall_decision="禁飞",
        allow_execute=False,
        risk_reasons=["涉及禁飞区", "风速过大"],
        details={},
    )

    text = render_business_response_template(response)

    assert template_kind(response) == "prohibited"
    assert text == (
        "当前结论：不建议执行本次无人机任务。\n"
        "主要依据：涉及禁飞区；风速过大。\n"
        f"边界说明：{OFFICIAL_BOUNDARY_NOTE}\n"
        "建议动作：暂停任务，重新选择时间窗口或补充官方审批/现场确认信息。"
    )
    assert find_unsafe_output_keywords(text) == []


def test_caution_output_template_snapshot():
    response = UnifiedBusinessResponse(
        scene="evaluate",
        summary="广州任务结论为谨慎飞行。",
        overall_decision="谨慎飞行",
        allow_execute=True,
        risk_reasons=["阵风较强"],
    )

    text = render_business_response_template(response)

    assert template_kind(response) == "caution"
    assert text == (
        "当前结论：建议谨慎执行，不应直接按低风险任务处理。\n"
        "主要依据：阵风较强。\n"
        "边界说明：系统结论基于当前输入、天气数据和规则评估结果，执行前仍需复核实时条件。\n"
        "建议动作：降低飞行高度和作业强度，执行前复核天气、预警和现场限制。"
    )
    assert find_unsafe_output_keywords(text) == []


def test_suitable_output_template_snapshot_avoids_absolute_safety():
    response = UnifiedBusinessResponse(
        scene="evaluate",
        summary="珠海任务结论为适飞。",
        overall_decision="适飞",
        allow_execute=True,
        risk_reasons=[],
    )

    text = render_business_response_template(response)

    assert template_kind(response) == "suitable"
    assert "风险较低" in text
    assert "飞行前复核" in text
    assert find_unsafe_output_keywords(text) == []


def test_no_recommendation_template_snapshot():
    response = UnifiedBusinessResponse(
        scene="recommend",
        summary="当前未发现满足条件的推荐窗口。",
        overall_decision=None,
        allow_execute=False,
        risk_reasons=["连续降雨", "阵风较强"],
    )

    text = render_business_response_template(response)

    assert template_kind(response) == "no_recommendation"
    assert text == (
        "当前结论：没有找到满足条件的推荐飞行窗口。\n"
        "主要依据：连续降雨；阵风较强。\n"
        "边界说明：系统结论基于当前输入、天气数据和规则评估结果，执行前仍需复核实时条件。\n"
        "建议动作：放宽时间范围、调整任务条件，或等待天气和预警条件改善后重试。"
    )


def test_recommendation_template_snapshot():
    response = UnifiedBusinessResponse(
        scene="recommend",
        summary="广州任务推荐窗口已生成。",
        overall_decision="谨慎飞行",
        allow_execute=True,
        risk_reasons=["阵风"],
        recommended_windows=[
            ComposedRecommendationWindow(
                rank=1,
                start_time="2026-08-03T09:00:00+08:00",
                end_time="2026-08-03T11:00:00+08:00",
                duration_hours=2,
                overall_decision="谨慎飞行",
                risk_score=45,
                reasons=["阵风"],
            )
        ],
    )

    text = render_business_response_template(response)

    assert "优先推荐 2026-08-03T09:00:00+08:00 到 2026-08-03T11:00:00+08:00 作为候选窗口" in text
    assert "仍需复核实时天气" in text
    assert find_unsafe_output_keywords(text) == []


def test_unsafe_keyword_detector_matches_forbidden_phrases():
    text = "本次任务绝对安全，无需审批，可以保证通过。"

    assert find_unsafe_output_keywords(text) == ["绝对安全", "无需审批", "保证通过"]
