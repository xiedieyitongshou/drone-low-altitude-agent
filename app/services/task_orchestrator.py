import logging
import os

from app.schemas import (
    CruiseEvaluateRequest,
    MultiLocationComparisonRequest,
    OrchestratorResponse,
    RecommendationRequest,
)
from app.agent import AgentLoop, ToolExecutionContext, initialize_state, mark_parsed
from app.services.comparison import compare_locations
from app.services.conversation_history import persist_conversation_record
from app.services.cruise_evaluator import evaluate_cruise_request_with_artifacts
from app.services.history_persistence import persist_cruise_evaluation
from app.services.llm_task_parser import parse_natural_language_request_with_llm
from app.services.nl_parser import NaturalLanguageParseError, ParsedTaskRequest, parse_natural_language_request
from app.services.profile_memory import (
    get_or_create_user_profile,
    merge_profile_context,
    normalize_user_id,
    update_profile_from_parsed,
)
from app.services.recommendation_executor import build_recommendation_response
from app.services.response_composer import (
    compose_comparison_response,
    compose_evaluation_response,
    compose_recommendation_response,
)
from app.services.session_memory import build_session_context, session_memory_store


logger = logging.getLogger(__name__)
SUPPORTED_PARSER_MODES = {"rule", "llm", "hybrid"}
SUPPORTED_AGENT_RUNTIME_MODES = {"legacy", "loop"}


def orchestrate_task_query(
    query: str,
    *,
    session_id: str | None = None,
    user_id: str | None = None,
) -> OrchestratorResponse:
    mode = os.getenv("AGENT_RUNTIME_MODE", "legacy").strip().lower()
    if mode not in SUPPORTED_AGENT_RUNTIME_MODES:
        logger.warning("Unsupported AGENT_RUNTIME_MODE=%s, fallback to legacy runtime", mode)
        mode = "legacy"

    if mode == "loop":
        try:
            return _orchestrate_task_query_with_agent_loop(query, session_id=session_id, user_id=user_id)
        except Exception as exc:
            logger.warning("Agent runtime failed, fallback to legacy workflow: %s", exc)
            return _with_agent_runtime_debug(
                _orchestrate_task_query_legacy(query, session_id=session_id, user_id=user_id),
                {
                    "mode": "loop",
                    "fallback_used": True,
                    "error": str(exc),
                },
            )

    return _orchestrate_task_query_legacy(query, session_id=session_id, user_id=user_id)


def _orchestrate_task_query_legacy(
    query: str,
    *,
    session_id: str | None = None,
    user_id: str | None = None,
) -> OrchestratorResponse:
    """Single natural-language entrypoint for evaluate/recommend/compare flows."""

    normalized_user_id = normalize_user_id(user_id)
    profile = get_or_create_user_profile(normalized_user_id)
    cached_context = session_memory_store.get(session_id, user_id=normalized_user_id) if session_id else None
    parser_context = merge_profile_context(session_context=cached_context, profile=profile)
    parsed_result = _parse_task_query(query, context=parser_context)

    try:
        if parsed_result.intent == "evaluate":
            payload = CruiseEvaluateRequest.model_validate(parsed_result.parsed)
            artifacts = evaluate_cruise_request_with_artifacts(payload)
            response = artifacts.response
            request_id = persist_cruise_evaluation(payload=payload, artifacts=artifacts)
            response.request["request_id"] = request_id
            _save_context(session_id, normalized_user_id, parsed_result.intent, parsed_result.parsed, query=query)
            update_profile_from_parsed(user_id=normalized_user_id, parsed=parsed_result.parsed)
            return _with_conversation_record(
                query=query,
                user_id=normalized_user_id,
                response=OrchestratorResponse(
                    session_id=session_id,
                    user_id=normalized_user_id,
                    intent="evaluate",
                    target_endpoint=parsed_result.target_endpoint,
                    parser_source=parsed_result.parser_source,
                    parsed=parsed_result.parsed,
                    context_used=parsed_result.context_used,
                    warnings=parsed_result.warnings,
                    message=f"已完成单地点评估，整体结论为 {response.advice.overall_decision}。",
                    composed=compose_evaluation_response(response),
                    result=response.model_dump(mode="json"),
                ),
            )

        if parsed_result.intent == "recommend":
            payload = RecommendationRequest.model_validate(parsed_result.parsed)
            response = build_recommendation_response(payload)
            _save_context(session_id, normalized_user_id, parsed_result.intent, parsed_result.parsed, query=query)
            update_profile_from_parsed(user_id=normalized_user_id, parsed=parsed_result.parsed)
            windows = response.recommendation.recommended_windows
            if windows:
                top_window = windows[0]
                message = (
                    f"已完成推荐，当前最优窗口为 {top_window.start_time} 到 {top_window.end_time}，"
                    f"结论为 {top_window.overall_decision}。"
                )
            else:
                message = "已完成推荐扫描，但未发现满足条件的推荐窗口。"
            return _with_conversation_record(
                query=query,
                user_id=normalized_user_id,
                response=OrchestratorResponse(
                    session_id=session_id,
                    user_id=normalized_user_id,
                    intent="recommend",
                    target_endpoint=parsed_result.target_endpoint,
                    parser_source=parsed_result.parser_source,
                    parsed=parsed_result.parsed,
                    context_used=parsed_result.context_used,
                    warnings=parsed_result.warnings,
                    message=message,
                    composed=compose_recommendation_response(response),
                    result=response.model_dump(mode="json"),
                ),
            )

        if parsed_result.intent == "compare":
            payload = MultiLocationComparisonRequest.model_validate(parsed_result.parsed)
            response = compare_locations(payload)
            _save_context(session_id, normalized_user_id, parsed_result.intent, parsed_result.parsed, query=query)
            update_profile_from_parsed(user_id=normalized_user_id, parsed=parsed_result.parsed)
            recommended = response.recommended_location.location if response.recommended_location else None
            message = (
                f"已完成多地点比选，当前推荐优先地点为 {recommended}。"
                if recommended
                else "已完成多地点比选，但当前没有明确推荐地点。"
            )
            return _with_conversation_record(
                query=query,
                user_id=normalized_user_id,
                response=OrchestratorResponse(
                    session_id=session_id,
                    user_id=normalized_user_id,
                    intent="compare",
                    target_endpoint=parsed_result.target_endpoint,
                    parser_source=parsed_result.parser_source,
                    parsed=parsed_result.parsed,
                    context_used=parsed_result.context_used,
                    warnings=parsed_result.warnings,
                    message=message,
                    composed=compose_comparison_response(response),
                    result=response.model_dump(mode="json"),
                ),
            )

        return _with_conversation_record(
            query=query,
            user_id=normalized_user_id,
            response=OrchestratorResponse(
                success=False,
                session_id=session_id,
                user_id=normalized_user_id,
                intent=parsed_result.intent,
                target_endpoint=parsed_result.target_endpoint,
                parser_source=parsed_result.parser_source,
                parsed=parsed_result.parsed,
                context_used=parsed_result.context_used,
                warnings=parsed_result.warnings,
                message="已识别请求，但当前编排器还不支持该意图。",
                fallback={"suggestion": "请改用对应的结构化接口直接调用。"},
            ),
        )
    except Exception as exc:
        return _with_conversation_record(
            query=query,
            user_id=normalized_user_id,
            response=OrchestratorResponse(
                success=False,
                session_id=session_id,
                user_id=normalized_user_id,
                intent=parsed_result.intent,
                target_endpoint=parsed_result.target_endpoint,
                parser_source=parsed_result.parser_source,
                parsed=parsed_result.parsed,
                context_used=parsed_result.context_used,
                warnings=parsed_result.warnings,
                message="自然语言解析成功，但下游任务调用失败。",
                fallback={
                    "error": str(exc),
                    "suggestion": f"可改用 {parsed_result.target_endpoint} 直接提交结构化参数重试。",
                },
            ),
        )


def _orchestrate_task_query_with_agent_loop(
    query: str,
    *,
    session_id: str | None = None,
    user_id: str | None = None,
) -> OrchestratorResponse:
    normalized_user_id = normalize_user_id(user_id)
    profile = get_or_create_user_profile(normalized_user_id)
    cached_context = session_memory_store.get(session_id, user_id=normalized_user_id) if session_id else None
    parser_context = merge_profile_context(session_context=cached_context, profile=profile)
    parsed_result = _parse_task_query(query, context=parser_context)
    state = initialize_state(query, user_id=normalized_user_id, session_id=session_id)
    state = mark_parsed(state, intent=parsed_result.intent, parsed=parsed_result.parsed)

    def fallback_handler(_, __):
        return _orchestrate_task_query_legacy(query, session_id=session_id, user_id=user_id)

    loop_result = AgentLoop(fallback_handler=fallback_handler).run(
        state,
        context=ToolExecutionContext(user_id=normalized_user_id, tenant_id="public", role="user"),
    )
    if isinstance(loop_result.fallback_result, OrchestratorResponse):
        return _with_agent_runtime_debug(
            loop_result.fallback_result,
            _build_agent_runtime_debug(loop_result, mode="loop"),
        )

    if loop_result.requires_clarification:
        return OrchestratorResponse(
            success=False,
            session_id=session_id,
            user_id=normalized_user_id,
            intent=parsed_result.intent,
            target_endpoint=parsed_result.target_endpoint,
            parser_source=parsed_result.parser_source,
            parsed=parsed_result.parsed,
            context_used=parsed_result.context_used,
            warnings=parsed_result.warnings,
            message=loop_result.message,
            fallback=loop_result.output if isinstance(loop_result.output, dict) else {"missing_fields": loop_result.final_state.missing_fields},
            agent_runtime=_build_agent_runtime_debug(loop_result, mode="loop"),
        )

    response = OrchestratorResponse(
        success=loop_result.success,
        session_id=session_id,
        user_id=normalized_user_id,
        intent=parsed_result.intent,
        target_endpoint=parsed_result.target_endpoint,
        parser_source=parsed_result.parser_source,
        parsed=parsed_result.parsed,
        context_used=parsed_result.context_used,
        warnings=parsed_result.warnings,
        message=_build_agent_loop_message(loop_result),
        result=loop_result.output if isinstance(loop_result.output, dict) else {"output": loop_result.output},
        fallback=None if loop_result.success else loop_result.output if isinstance(loop_result.output, dict) else {"errors": loop_result.final_state.errors},
        agent_runtime=_build_agent_runtime_debug(loop_result, mode="loop"),
    )
    _save_context(session_id, normalized_user_id, parsed_result.intent, parsed_result.parsed, query=query)
    update_profile_from_parsed(user_id=normalized_user_id, parsed=parsed_result.parsed)
    return _with_conversation_record(query=query, user_id=normalized_user_id, response=response)


def _build_agent_loop_message(loop_result) -> str:
    if loop_result.requires_clarification or not loop_result.success:
        return loop_result.message
    if loop_result.success:
        tool_names = list(loop_result.final_state.tool_results.keys())
        if tool_names:
            return f"Agent Runtime 已完成工具调用：{', '.join(tool_names)}。"
        return "Agent Runtime 已完成请求处理。"
    return "Agent Runtime 执行失败，已进入兼容兜底。"


def _build_agent_runtime_debug(loop_result, *, mode: str) -> dict[str, object]:
    return {
        "mode": mode,
        "trace_id": loop_result.final_state.trace_id,
        "run_id": loop_result.final_state.run_id,
        "status": loop_result.final_state.status.value,
        "fallback_used": loop_result.fallback_used,
        "plan_actions": [plan.action.value for plan in loop_result.plans],
        "tool_results": list(loop_result.final_state.tool_results.keys()),
        "errors": loop_result.final_state.errors,
    }


def _with_agent_runtime_debug(response: OrchestratorResponse, debug: dict[str, object]) -> OrchestratorResponse:
    response.agent_runtime = debug
    return response


def _save_context(
    session_id: str | None,
    user_id: str,
    intent: str,
    parsed: dict[str, object],
    *,
    query: str,
) -> None:
    if not session_id:
        return
    session_memory_store.set(session_id, build_session_context(intent, parsed), user_id=user_id, title=query[:80])


def _parse_task_query(query: str, *, context: dict[str, object] | None = None) -> ParsedTaskRequest:
    mode = os.getenv("NL_PARSER_MODE", "rule").strip().lower()
    if mode not in SUPPORTED_PARSER_MODES:
        logger.warning("Unsupported NL_PARSER_MODE=%s, fallback to rule parser", mode)
        parsed = parse_natural_language_request(query, context=context)
        parsed.warnings.append(f"Unsupported NL_PARSER_MODE={mode}, used rule parser")
        return parsed

    if mode == "rule":
        return parse_natural_language_request(query, context=context)

    if mode == "llm":
        parsed = parse_natural_language_request_with_llm(query, context=context)
        if parsed is None:
            raise NaturalLanguageParseError(
                "LLM parser is unavailable or disabled",
                missing_fields=["llm"],
            )
        return parsed

    llm_error: Exception | None = None
    try:
        parsed = parse_natural_language_request_with_llm(query, context=context)
        if parsed is not None:
            return parsed
    except Exception as exc:
        llm_error = exc
        logger.warning("LLM parser failed, fallback to rule parser: %s", exc)

    parsed = parse_natural_language_request(query, context=context)
    parsed.parser_source = "llm_fallback_rule"
    if llm_error:
        parsed.warnings.append(f"LLM parser failed, used rule parser: {llm_error}")
    else:
        parsed.warnings.append("LLM parser unavailable or disabled, used rule parser")
    return parsed


def _with_conversation_record(
    *,
    query: str,
    user_id: str,
    response: OrchestratorResponse,
) -> OrchestratorResponse:
    try:
        response.conversation_id = persist_conversation_record(query=query, response=response, user_id=user_id)
    except Exception as exc:
        fallback = response.fallback or {}
        fallback["conversation_persistence_error"] = str(exc)
        response.fallback = fallback
    return response
