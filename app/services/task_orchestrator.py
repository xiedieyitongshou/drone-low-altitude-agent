from app.schemas import (
    CruiseEvaluateRequest,
    MultiLocationComparisonRequest,
    OrchestratorResponse,
    RecommendationRequest,
)
from app.services.comparison import compare_locations
from app.services.cruise_evaluator import evaluate_cruise_request_with_artifacts
from app.services.history_persistence import persist_cruise_evaluation
from app.services.nl_parser import parse_natural_language_request
from app.services.recommendation_executor import build_recommendation_response


def orchestrate_task_query(query: str) -> OrchestratorResponse:
    parsed_result = parse_natural_language_request(query)

    try:
        if parsed_result.intent == "evaluate":
            payload = CruiseEvaluateRequest.model_validate(parsed_result.parsed)
            artifacts = evaluate_cruise_request_with_artifacts(payload)
            response = artifacts.response
            request_id = persist_cruise_evaluation(payload=payload, artifacts=artifacts)
            response.request["request_id"] = request_id
            return OrchestratorResponse(
                intent="evaluate",
                target_endpoint=parsed_result.target_endpoint,
                parsed=parsed_result.parsed,
                warnings=parsed_result.warnings,
                message=f"已完成单地点评估，整体结论为{response.advice.overall_decision}。",
                result=response.model_dump(mode="json"),
            )

        if parsed_result.intent == "recommend":
            payload = RecommendationRequest.model_validate(parsed_result.parsed)
            response = build_recommendation_response(payload)
            windows = response.recommendation.recommended_windows
            if windows:
                top_window = windows[0]
                message = (
                    f"已完成推荐，当前最优窗口为 {top_window.start_time} 到 {top_window.end_time}，"
                    f"结论为{top_window.overall_decision}。"
                )
            else:
                message = "已完成推荐扫描，但未发现满足条件的推荐窗口。"
            return OrchestratorResponse(
                intent="recommend",
                target_endpoint=parsed_result.target_endpoint,
                parsed=parsed_result.parsed,
                warnings=parsed_result.warnings,
                message=message,
                result=response.model_dump(mode="json"),
            )

        if parsed_result.intent == "compare":
            payload = MultiLocationComparisonRequest.model_validate(parsed_result.parsed)
            response = compare_locations(payload)
            recommended = response.recommended_location.location if response.recommended_location else None
            message = (
                f"已完成多地点比选，当前推荐优先地点为{recommended}。"
                if recommended
                else "已完成多地点比选，但当前没有明确推荐地点。"
            )
            return OrchestratorResponse(
                intent="compare",
                target_endpoint=parsed_result.target_endpoint,
                parsed=parsed_result.parsed,
                warnings=parsed_result.warnings,
                message=message,
                result=response.model_dump(mode="json"),
            )

        return OrchestratorResponse(
            success=False,
            intent=parsed_result.intent,
            target_endpoint=parsed_result.target_endpoint,
            parsed=parsed_result.parsed,
            warnings=parsed_result.warnings,
            message="已识别请求，但当前编排器还不支持该意图。",
            fallback={"suggestion": "请改用对应的结构化接口直接调用。"},
        )
    except Exception as exc:
        return OrchestratorResponse(
            success=False,
            intent=parsed_result.intent,
            target_endpoint=parsed_result.target_endpoint,
            parsed=parsed_result.parsed,
            warnings=parsed_result.warnings,
            message="自然语言解析成功，但下游任务调用失败。",
            fallback={
                "error": str(exc),
                "suggestion": f"可改用 {parsed_result.target_endpoint} 直接提交结构化参数重试。",
            },
        )
