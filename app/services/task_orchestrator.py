import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from app.schemas import (
    CruiseEvaluateRequest,
    MultiLocationComparisonRequest,
    OrchestratorResponse,
    RecommendationRequest,
    CruiseAssessmentResponse,
)
from app.schemas.composed_response import UnifiedBusinessResponse
from app.agent import (
    AgentLoop,
    AgentRouteKind,
    ToolExecutionContext,
    build_route_tool_input,
    default_tool_registry,
    get_business_route,
    initialize_state,
    mark_parsed,
)
from app.agent.context_manager import (
    build_agent_parser_context,
    build_pending_task_context,
    merge_agent_context,
)
from app.services.comparison import compare_locations
from app.services.conversation_history import persist_conversation_record
from app.services.cruise_evaluator import evaluate_cruise_request_with_artifacts
from app.services.history_persistence import persist_cruise_evaluation
from app.services.llm_task_parser import parse_natural_language_request_with_llm
from app.services.nl_parser import KNOWLEDGE_HINTS, NaturalLanguageParseError, ParsedTaskRequest, parse_natural_language_request
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
from app.services.run_observability import current_observation, measure_stage, observe_run, timed_stage


logger = logging.getLogger(__name__)
SUPPORTED_PARSER_MODES = {"rule", "llm", "hybrid"}
SUPPORTED_AGENT_RUNTIME_MODES = {"legacy", "loop"}


def orchestrate_task_query(
    query: str,
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    db: Session | None = None,
) -> OrchestratorResponse:
    with observe_run(user_id=normalize_user_id(user_id), session_id=session_id) as observation:
        observation.emit("state_update", status_after="initialized", input_payload={"query": query})
        try:
            response = _execute_task_query(query, session_id=session_id, user_id=user_id, db=db)
        except Exception as exc:
            observation.emit("error", error_code="ORCHESTRATION_FAILED", metadata={"error_type": type(exc).__name__})
            observation.emit("final_response", status_after="failed", metadata={"outcome": "failed", "timings": observation.timing_summary()})
            if db is not None:
                db.rollback()
            _flush_observation(observation, db=db)
            raise
        response.trace_id = observation.trace_id
        response.agent_runtime = {
            **(response.agent_runtime or {"mode": "legacy"}),
            "trace_id": observation.trace_id, "run_id": observation.run_id,
        }
        _attach_evaluation_result(response)
        if not response.success and db is not None:
            db.rollback()
        timings = observation.timing_summary()
        response.agent_runtime["timings"] = timings
        response = _with_conversation_record(query=query, user_id=observation.user_id, response=response, final=True, db=db)
        runtime = response.agent_runtime or {}
        outcome = "clarification" if runtime.get("status") == "needs_clarification" else "success" if response.success else "failed"
        if response.warnings and outcome == "success":
            outcome = "degraded"
        if outcome == "success" and runtime.get("fallback_used"):
            outcome = "degraded"
        if outcome == "success" and any(not sample["ok"] and sample["stage"] in {"llm", "knowledge", "composition"}
                                        for sample in observation.samples):
            outcome = "degraded"
        if outcome == "failed" and not any(event.event_type == "error" for event in observation.events):
            observation.emit("error", error_code=str((response.fallback or {}).get("error_code") or "AGENT_REQUEST_FAILED"))
        observation.emit(
            "final_response", status_after="needs_clarification" if outcome == "clarification" else "completed" if response.success else "failed",
            output_payload={"success": response.success, "message": response.message},
            metadata={"outcome": outcome, "request_id": response.request_id,
                      "conversation_id": response.conversation_id, "timings": timings,
                      "fallback_used": bool(runtime.get("fallback_used")), "warnings": response.warnings},
        )
        if not _flush_observation(observation, db=db):
            response.warnings.append("执行记录保存失败，本次业务结果仍可使用。")
        return response


def _flush_observation(observation, *, db: Session | None = None) -> bool:
    try:
        observation.flush(db=db)
        return True
    except Exception:
        if db is not None:
            db.rollback()
        logger.exception("Could not persist Agent Trace", extra={"trace_id": observation.trace_id})
        return False


def _attach_evaluation_result(response: OrchestratorResponse) -> None:
    result = response.result or {}
    tools = result.get("tool_results", {})
    data = tools.get("evaluate_flight_risk", {}).get("data") if isinstance(tools, dict) else None
    if not isinstance(data, dict) and isinstance(tools, dict):
        data = next((item.get("data") for item in tools.values() if isinstance(item, dict)
                     and isinstance(item.get("data"), dict) and isinstance(item["data"].get("request"), dict)), None)
    if not isinstance(data, dict) and isinstance(result.get("request"), dict):
        data = result
    if not isinstance(data, dict):
        return
    request = data.get("request", {})
    response.request_id = request.get("request_id")
    if request.get("persistence_status") == "failed":
        response.warnings.append("评估已完成，但历史快照保存失败。")
    if response.intent != "evaluate" or response.composed is not None or "advice" not in data:
        return
    assessment = CruiseAssessmentResponse.model_validate(data)
    try:
        response.composed = compose_evaluation_response(assessment)
        if response.composed.details.get("knowledge_retrieval_status") == "error":
            response.warnings.append("知识建议暂不可用，已保留规则评估结论。")
            observation = current_observation()
            if observation:
                observation.emit("error", error_code="KNOWLEDGE_UNAVAILABLE")
    except Exception as exc:
        logger.exception("Evaluation composition failed", extra={"trace_id": response.trace_id})
        observation = current_observation()
        if observation:
            observation.emit("error", error_code="COMPOSITION_FAILED", metadata={"error_type": type(exc).__name__})
        response.warnings.append("知识建议或解释暂不可用，已保留规则评估结论。")
        from app.services.risk_output_templates import render_business_response_template

        composed = UnifiedBusinessResponse(
            scene="evaluate", summary=f"任务结论为 {assessment.advice.overall_decision}。",
            overall_decision=assessment.advice.overall_decision, allow_execute=assessment.advice.allow_cruise,
            risk_reasons=assessment.advice.summary_risk_factors, details={"request": assessment.request},
        )
        composed.explanation = render_business_response_template(composed)
        composed.explanation_source = "template"
        response.composed = composed


def _execute_task_query(
    query: str,
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    db: Session | None = None,
) -> OrchestratorResponse:
    mode = os.getenv("AGENT_RUNTIME_MODE", "legacy").strip().lower()
    if mode not in SUPPORTED_AGENT_RUNTIME_MODES:
        logger.warning("Unsupported AGENT_RUNTIME_MODE=%s, fallback to legacy runtime", mode)
        mode = "legacy"

    if mode == "loop":
        try:
            return _orchestrate_task_query_with_agent_loop(query, session_id=session_id, user_id=user_id, db=db)
        except Exception:
            logger.exception("Agent runtime failed", extra={"session_id": session_id, "user_id": user_id})
            return OrchestratorResponse(
                success=False,
                session_id=session_id,
                user_id=normalize_user_id(user_id),
                intent="unknown",
                target_endpoint="/agent/query",
                parsed={},
                message="本轮请求处理失败。",
                fallback={"error_code": "AGENT_RUNTIME_ERROR"},
                agent_runtime={"mode": "loop", "fallback_used": False, "status": "failed"},
            )

    return _orchestrate_task_query_legacy(query, session_id=session_id, user_id=user_id, db=db)


def _orchestrate_task_query_legacy(
    query: str,
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    db: Session | None = None,
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
            request_id = persist_cruise_evaluation(payload=payload, artifacts=artifacts, user_id=normalized_user_id, db=db)
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

        if _is_mission_task_intent(parsed_result.intent):
            return _handle_legacy_mission_task_intent(
                query=query,
                session_id=session_id,
                user_id=normalized_user_id,
                parsed_result=parsed_result,
                db=db,
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
    db: Session | None = None,
) -> OrchestratorResponse:
    normalized_user_id = normalize_user_id(user_id)
    with measure_stage("context_read"):
        profile = get_or_create_user_profile(normalized_user_id)
        cached_context = session_memory_store.get(session_id, user_id=normalized_user_id) if session_id else None
        parser_context = build_agent_parser_context(session_context=cached_context, profile=profile)
    knowledge_city = cached_context.get("city") if cached_context else None
    try:
        parsed_result = _parse_task_query(query, context=parser_context, defer_context_merge=True)
    except NaturalLanguageParseError as exc:
        return _handle_agent_parse_error(
            query=query,
            session_id=session_id,
            user_id=normalized_user_id,
            error=exc,
            knowledge_city=knowledge_city,
        )
    observation = current_observation()
    if observation:
        observation.emit("parse", output_payload=parsed_result.parsed, metadata={"intent": parsed_result.intent, "parser_source": parsed_result.parser_source})
    context_result = merge_agent_context(
        intent=parsed_result.intent,
        parsed=parsed_result.parsed,
        session_context=cached_context,
        profile=profile,
    )
    if observation:
        observation.emit("state_update", output_payload=context_result.parsed, metadata={
            "source": "context_merge", "field_sources": context_result.field_sources,
            "missing_fields": context_result.missing_fields, "modified_fields": context_result.modified_fields,
        })
    if parsed_result.intent == "knowledge":
        context_result.parsed["constraint_sources"] = {
            field: source for field, source in context_result.field_sources.items()
            if field in {"city", "province", "region", "as_of", "task_type", "warning_types", "warning_levels"}
        }
    parsed_result = parsed_result.__class__(
        intent=context_result.intent,
        target_endpoint=parsed_result.target_endpoint,
        parsed=context_result.parsed,
        warnings=parsed_result.warnings,
        context_used=parsed_result.context_used or context_result.context_used,
        parser_source=parsed_result.parser_source,
    )
    state = initialize_state(query, user_id=normalized_user_id, session_id=session_id)
    state = mark_parsed(
        state,
        intent=parsed_result.intent,
        parsed=parsed_result.parsed,
        missing_fields=context_result.missing_fields,
    )

    def fallback_handler(_, __):
        return _orchestrate_task_query_legacy(query, session_id=session_id, user_id=user_id, db=db)

    route = get_business_route(parsed_result.intent)
    legacy_handler = fallback_handler if route and route.route_kind == AgentRouteKind.BUSINESS_COMPUTE else None
    loop_result = AgentLoop(fallback_handler=legacy_handler).run(
        state,
        context=ToolExecutionContext(user_id=normalized_user_id, tenant_id="public", role="user", db=db),
    )
    if isinstance(loop_result.fallback_result, OrchestratorResponse):
        return _with_agent_runtime_debug(
            loop_result.fallback_result,
            _build_agent_runtime_debug(loop_result, mode="loop", context_result=context_result),
        )

    if loop_result.requires_clarification:
        pending_parsed = parsed_result.parsed
        if parsed_result.intent == "create_task":
            pending_parsed = {
                key: value
                for key, value in pending_parsed.items()
                if context_result.field_sources[key] in {"session", "user_input"}
            }
        _save_pending_task(
            session_id=session_id,
            user_id=normalized_user_id,
            intent=parsed_result.intent,
            parsed=pending_parsed,
            missing_fields=loop_result.final_state.missing_fields,
            query=query,
            knowledge_city=knowledge_city,
        )
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
            agent_runtime=_build_agent_runtime_debug(loop_result, mode="loop", context_result=context_result),
        )

    session_parsed = _enrich_task_session_context(parsed_result.parsed, loop_result)
    response = OrchestratorResponse(
        success=loop_result.success,
        session_id=session_id,
        user_id=normalized_user_id,
        intent=parsed_result.intent,
        target_endpoint=parsed_result.target_endpoint,
        parser_source=parsed_result.parser_source,
        parsed=session_parsed,
        context_used=parsed_result.context_used,
        warnings=parsed_result.warnings,
        message=_build_agent_loop_message(loop_result),
        result=loop_result.output if isinstance(loop_result.output, dict) else {"output": loop_result.output},
        fallback=None if loop_result.success else loop_result.output if isinstance(loop_result.output, dict) else {"errors": loop_result.final_state.errors},
        agent_runtime=_build_agent_runtime_debug(loop_result, mode="loop", context_result=context_result),
    )
    if parsed_result.intent == "knowledge" and context_result.field_sources.get("city") == "user_input":
        knowledge_city = session_parsed["city"]
    if loop_result.success:
        _save_completed_context(response, query=query, knowledge_city=knowledge_city)
    return _with_conversation_record(query=query, user_id=normalized_user_id, response=response)


def _handle_agent_parse_error(
    *,
    query: str,
    session_id: str | None,
    user_id: str,
    error: NaturalLanguageParseError,
    knowledge_city: object = None,
) -> OrchestratorResponse:
    intent = error.intent or "unknown"
    target_endpoint = error.target_endpoint or "/agent/query"
    parsed = _clean_context_fields(error.parsed)
    observation = current_observation()
    if observation:
        observation.emit("parse", output_payload=parsed, metadata={"intent": intent, "missing_fields": error.missing_fields})
    state = initialize_state(query, user_id=user_id, session_id=session_id)
    state = mark_parsed(state, intent=intent, parsed=parsed, missing_fields=error.missing_fields)
    loop_result = AgentLoop().run(state, context=ToolExecutionContext(user_id=user_id, tenant_id="public", role="user"))

    _save_pending_task(
        session_id=session_id,
        user_id=user_id,
        intent=intent,
        parsed=parsed,
        missing_fields=error.missing_fields,
        query=query,
        knowledge_city=knowledge_city,
    )

    return _with_conversation_record(
        query=query,
        user_id=user_id,
        response=OrchestratorResponse(
            success=False,
            session_id=session_id,
            user_id=user_id,
            intent=intent,
            target_endpoint=target_endpoint,
            parser_source="rule",
            parsed=parsed,
            context_used=False,
            warnings=error.warnings,
            message=loop_result.message,
            fallback=loop_result.output if isinstance(loop_result.output, dict) else {"missing_fields": error.missing_fields},
            agent_runtime=_build_agent_runtime_debug(loop_result, mode="loop"),
        ),
    )


def _handle_legacy_mission_task_intent(
    *,
    query: str,
    session_id: str | None,
    user_id: str,
    parsed_result: ParsedTaskRequest,
    db: Session | None,
) -> OrchestratorResponse:
    route = get_business_route(parsed_result.intent)
    if route is None:
        raise ValueError(f"unsupported mission task intent: {parsed_result.intent}")

    tool_input = build_route_tool_input(route, parsed_result.parsed)
    tool_result = default_tool_registry.call(
        route.primary_tool,
        tool_input,
        context=ToolExecutionContext(user_id=user_id, tenant_id="public", role="user", db=db),
    )
    session_parsed = _enrich_task_session_context_from_results(parsed_result.parsed, [tool_result])
    response = OrchestratorResponse(
        success=tool_result.success,
        session_id=session_id,
        user_id=user_id,
        intent=parsed_result.intent,
        target_endpoint=parsed_result.target_endpoint,
        parser_source=parsed_result.parser_source,
        parsed=session_parsed,
        context_used=parsed_result.context_used,
        warnings=parsed_result.warnings,
        message=_build_legacy_mission_task_message(parsed_result.intent, tool_result.success),
        result=tool_result.data if tool_result.success else None,
        fallback=None if tool_result.success else {
            "tool_name": tool_result.tool_name,
            "error_code": tool_result.error_code,
            "message": tool_result.message,
        },
    )
    if tool_result.success:
        _save_completed_context(response, query=query)
    return _with_conversation_record(query=query, user_id=user_id, response=response)


@timed_stage("session_write")
def _save_pending_task(
    *,
    session_id: str | None,
    user_id: str,
    intent: str,
    parsed: dict[str, object],
    missing_fields: list[str],
    query: str,
    knowledge_city: object = None,
) -> None:
    if not session_id or not missing_fields or intent == "unknown":
        return
    context = build_pending_task_context(
        intent=intent,
        parsed=parsed,
        missing_fields=missing_fields,
        query=query,
    )
    if knowledge_city:
        context["city"] = knowledge_city
    session_memory_store.set(session_id, context, user_id=user_id, title=query[:80])


def _clean_context_fields(values: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in values.items() if value not in (None, "", [])}


def _build_agent_loop_message(loop_result) -> str:
    if loop_result.requires_clarification or not loop_result.success:
        return loop_result.message
    tool_names = list(loop_result.final_state.tool_results.keys())
    if tool_names:
        return f"Agent Runtime 已完成工具调用：{', '.join(tool_names)}。"
    return "Agent Runtime 已完成请求处理。"


def _build_agent_runtime_debug(loop_result, *, mode: str, context_result=None) -> dict[str, object]:
    debug = {
        "mode": mode,
        "trace_id": loop_result.final_state.trace_id,
        "run_id": loop_result.final_state.run_id,
        "status": loop_result.final_state.status.value,
        "fallback_used": loop_result.fallback_used,
        "plan_actions": [plan.action.value for plan in loop_result.plans],
        "tool_results": list(loop_result.final_state.tool_results.keys()),
        "errors": loop_result.final_state.errors,
    }
    if context_result is not None:
        debug["context_merge"] = {
            "field_sources": context_result.field_sources,
            "modified_fields": context_result.modified_fields,
            "invalidated_tools": context_result.invalidated_tools,
        }
    return debug


def _enrich_task_session_context(parsed: dict[str, object], loop_result) -> dict[str, object]:
    return _enrich_task_session_context_from_results(parsed, loop_result.final_state.tool_results.values())


def _enrich_task_session_context_from_results(parsed: dict[str, object], tool_results) -> dict[str, object]:
    enriched = dict(parsed)
    for result in tool_results:
        if not result.success or not isinstance(result.data, dict):
            continue
        data: dict[str, Any] = result.data
        if result.tool_name in {"create_mission_task", "select_mission_task_window"}:
            task_id = data.get("id")
            if task_id:
                enriched["task_id"] = task_id
                enriched["current_task_id"] = task_id
            title = data.get("title")
            if title:
                enriched["task_title"] = title
                enriched["current_task_title"] = title
            selected_window = data.get("selected_window")
            if isinstance(selected_window, dict) and selected_window.get("rank"):
                enriched["selected_window_rank"] = selected_window["rank"]
        if result.tool_name == "recommend_mission_task_windows":
            recommendation = data.get("recommendation")
            if isinstance(recommendation, dict):
                windows = recommendation.get("recommended_windows")
                if isinstance(windows, list):
                    enriched["last_recommended_windows"] = windows
            request = data.get("request")
            if isinstance(request, dict) and request.get("task_id"):
                enriched["task_id"] = request["task_id"]
                enriched["current_task_id"] = request["task_id"]
        if result.tool_name in {"evaluate_mission_task", "preflight_check_mission_task"}:
            request = data.get("request")
            if isinstance(request, dict) and request.get("task_id"):
                enriched["task_id"] = request["task_id"]
                enriched["current_task_id"] = request["task_id"]
    return enriched


def _is_mission_task_intent(intent: str | None) -> bool:
    return intent in {
        "create_task",
        "evaluate_task",
        "recommend_task",
        "select_task_window",
        "preflight_check_task",
    }


def _build_legacy_mission_task_message(intent: str, success: bool) -> str:
    if not success:
        return "任务单工具调用失败。"
    messages = {
        "create_task": "已创建任务单。",
        "evaluate_task": "已完成任务单风险评估。",
        "recommend_task": "已完成任务单窗口推荐。",
        "select_task_window": "已选择任务单执行窗口。",
        "preflight_check_task": "已完成任务单执行前复核。",
    }
    return messages.get(intent, "已完成任务单操作。")


def _with_agent_runtime_debug(response: OrchestratorResponse, debug: dict[str, object]) -> OrchestratorResponse:
    response.agent_runtime = debug
    return response


def _save_completed_context(
    response: OrchestratorResponse, *, query: str, knowledge_city: object = None
) -> None:
    log_context = {"session_id": response.session_id, "user_id": response.user_id, "intent": response.intent}
    try:
        _save_context(
            response.session_id,
            response.user_id,
            response.intent,
            response.parsed,
            query=query,
            knowledge_city=knowledge_city,
        )
    except Exception:
        logger.exception("Could not save the completed request's Session", extra=log_context)
        response.warnings.append("会话上下文保存失败，下一轮可能需要重新补充信息。")
    try:
        update_profile_from_parsed(user_id=response.user_id, parsed=response.parsed)
    except Exception:
        logger.exception("Could not update Profile after a completed request", extra=log_context)
        response.warnings.append("用户偏好更新失败。")


@timed_stage("session_write")
def _save_context(
    session_id: str | None,
    user_id: str,
    intent: str,
    parsed: dict[str, object],
    *,
    query: str,
    knowledge_city: object = None,
) -> None:
    if not session_id:
        return
    context = build_session_context(intent, parsed, knowledge_city=knowledge_city)
    session_memory_store.set(session_id, context, user_id=user_id, title=query[:80])


@timed_stage("parser")
def _parse_task_query(
    query: str, *, context: dict[str, object] | None = None, defer_context_merge: bool = False
) -> ParsedTaskRequest:
    parser_kwargs = {"context": context, "defer_context_merge": defer_context_merge}
    mode = os.getenv("NL_PARSER_MODE", "rule").strip().lower()
    if mode not in SUPPORTED_PARSER_MODES:
        logger.warning("Unsupported NL_PARSER_MODE=%s, fallback to rule parser", mode)
        parsed = parse_natural_language_request(query, **parser_kwargs)
        parsed.warnings.append(f"Unsupported NL_PARSER_MODE={mode}, used rule parser")
        return parsed

    if mode == "rule":
        return parse_natural_language_request(query, **parser_kwargs)

    if mode == "llm":
        parsed = parse_natural_language_request_with_llm(query, **parser_kwargs)
        if parsed is None:
            raise NaturalLanguageParseError(
                "LLM parser is unavailable or disabled",
                missing_fields=["llm"],
            )
        return parsed

    rule_result = None
    if any(hint in query for hint in KNOWLEDGE_HINTS) or (context and context.get("intent") == "knowledge"):
        try:
            rule_result = parse_natural_language_request(query, **parser_kwargs)
        except NaturalLanguageParseError:
            pass
        if rule_result is not None and rule_result.intent == "knowledge":
            # The existing LLM parser can fill ambiguous knowledge fields when enabled.
            from app.services.llm_client import is_llm_enabled

            if not is_llm_enabled() or not rule_result.parsed.get("required_context_fields"):
                return rule_result

    llm_error: Exception | None = None
    try:
        parsed = parse_natural_language_request_with_llm(query, **parser_kwargs)
        if parsed is not None:
            if rule_result is not None and rule_result.intent == "knowledge" and parsed.intent != "knowledge":
                return rule_result
            return parsed
    except Exception as exc:
        llm_error = exc
        logger.warning("LLM parser failed, fallback to rule parser: %s", exc)

    parsed = rule_result or parse_natural_language_request(query, **parser_kwargs)
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
    final: bool = False,
    db: Session | None = None,
) -> OrchestratorResponse:
    if current_observation() is not None and not final:
        return response
    try:
        response.conversation_id = persist_conversation_record(query=query, response=response, user_id=user_id, db=db)
    except Exception as exc:
        response.conversation_id = None
        response.warnings.append("对话记录保存失败，本次业务结果仍可使用。")
        observation = current_observation()
        if observation:
            observation.emit("error", error_code="CONVERSATION_SAVE_FAILED", metadata={"error_type": type(exc).__name__})
        fallback = response.fallback or {}
        fallback["conversation_persistence_error"] = str(exc)
        response.fallback = fallback
    return response
