from collections.abc import Callable
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.agent.executor import ToolExecutor
from app.agent.failure_policy import ToolRecoveryAction, classify_tool_failure, failure_policy_metadata
from app.agent.fallback import build_agent_fallback_output, build_clarification_message, build_tool_failure_message
from app.agent.guardrail import (
    GuardrailAction,
    GuardrailResult,
    check_input_guardrail,
    check_output_guardrail,
    guardrail_metadata,
)
from app.agent.logging import log_agent_event
from app.agent.planner import AgentPlan, AgentPlanAction, plan_next_step
from app.agent.state import (
    AgentState,
    AgentStatus,
    mark_completed,
    mark_failed,
    mark_needs_clarification,
    mark_tool_running,
    record_tool_result,
)
from app.agent.tools import ToolExecutionContext, ToolRegistry, default_tool_registry
from app.agent.trace import TraceEventType, build_trace_event
from app.services.agent_trace import record_trace_event


FallbackHandler = Callable[[AgentState, AgentPlan | None], Any]


class AgentLoopResult(BaseModel):
    success: bool
    final_state: AgentState
    message: str
    output: Any = None
    requires_clarification: bool = False
    fallback_used: bool = False
    fallback_result: Any = None
    last_plan: AgentPlan | None = None
    plans: list[AgentPlan] = Field(default_factory=list)


class AgentLoop:
    def __init__(
        self,
        *,
        tool_registry: ToolRegistry = default_tool_registry,
        tool_executor: ToolExecutor | None = None,
        max_iterations: int = 5,
        fallback_handler: FallbackHandler | None = None,
    ) -> None:
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor or ToolExecutor(tool_registry=tool_registry)
        self.max_iterations = max(max_iterations, 1)
        self.fallback_handler = fallback_handler

    def run(
        self,
        state: AgentState,
        *,
        context: ToolExecutionContext | None = None,
    ) -> AgentLoopResult:
        plans: list[AgentPlan] = []
        current_state = state
        execution_context = context or ToolExecutionContext(user_id=state.user_id)
        input_guardrail = check_input_guardrail(current_state)
        self._record_guardrail_event(current_state, input_guardrail)
        if not input_guardrail.allowed:
            if input_guardrail.action == GuardrailAction.ASK_CLARIFICATION:
                current_state = mark_needs_clarification(
                    current_state,
                    [],
                    message=input_guardrail.reason,
                )
                return AgentLoopResult(
                    success=True,
                    final_state=current_state,
                    message=input_guardrail.reason,
                    output=build_agent_fallback_output(
                        state=current_state,
                        message=input_guardrail.reason,
                        guardrail_result=input_guardrail,
                    ),
                    requires_clarification=True,
                    plans=plans,
                )
            return self._fallback(
                current_state,
                None,
                plans=plans,
                error_code=input_guardrail.error_code or "INPUT_GUARDRAIL_BLOCKED",
                message=input_guardrail.reason,
                allow_legacy_fallback=False,
                guardrail_result=input_guardrail,
            )

        for _ in range(self.max_iterations):
            plan = plan_next_step(current_state, tool_registry=self.tool_registry)
            plans.append(plan)
            log_agent_event(
                logging.INFO,
                "agent plan generated",
                event="plan",
                state=current_state,
                plan_action=plan.action.value,
                tool_name=plan.tool_name,
                metadata={"reason": plan.reason, "missing_fields": plan.missing_fields},
            )

            if plan.action == AgentPlanAction.ASK_CLARIFICATION:
                clarification_message = build_clarification_message(plan.missing_fields)
                current_state = mark_needs_clarification(
                    current_state,
                    plan.missing_fields,
                    message=clarification_message,
                )
                log_agent_event(
                    logging.INFO,
                    "agent clarification required",
                    event="clarification",
                    state=current_state,
                    plan_action=plan.action.value,
                    metadata={"missing_fields": plan.missing_fields},
                )
                return AgentLoopResult(
                    success=True,
                    final_state=current_state,
                    message=clarification_message,
                    output=build_agent_fallback_output(
                        state=current_state,
                        message=clarification_message,
                    ),
                    requires_clarification=True,
                    last_plan=plan,
                    plans=plans,
                )

            if plan.action == AgentPlanAction.CALL_TOOL:
                if not plan.tool_name:
                    return self._fallback(
                        current_state,
                        plan,
                        plans=plans,
                        error_code="INVALID_PLAN",
                        message="call_tool plan requires tool_name",
                    )

                current_state = mark_tool_running(
                    current_state,
                    tool_name=plan.tool_name,
                    tool_input=plan.tool_input,
                )
                tool_result = self.tool_executor.execute(
                    tool_name=plan.tool_name,
                    tool_input=plan.tool_input,
                    state=current_state,
                    context=execution_context,
                )
                current_state = record_tool_result(
                    current_state,
                    tool_name=plan.tool_name,
                    tool_result=tool_result,
                )
                if not tool_result.success:
                    failure_policy = classify_tool_failure(tool_result)
                    if failure_policy and failure_policy.recovery_action == ToolRecoveryAction.DIRECT_RESPONSE:
                        direct_message = build_tool_failure_message(
                            policy=failure_policy,
                            tool_result=tool_result,
                            tool_name=plan.tool_name,
                        )
                        current_state = mark_completed(current_state, message=direct_message)
                        return AgentLoopResult(
                            success=True,
                            final_state=current_state,
                            message=direct_message,
                            output=build_agent_fallback_output(
                                state=current_state,
                                message=direct_message,
                                policy=failure_policy,
                                tool_name=plan.tool_name,
                            ),
                            last_plan=plan,
                            plans=plans,
                        )
                    if failure_policy and failure_policy.recovery_action == ToolRecoveryAction.DENY:
                        return self._fallback(
                            current_state,
                            plan,
                            plans=plans,
                            error_code=tool_result.error_code or "PERMISSION_DENIED",
                            message=build_tool_failure_message(
                                policy=failure_policy,
                                tool_result=tool_result,
                                tool_name=plan.tool_name,
                            ),
                            allow_legacy_fallback=False,
                        )
                    return self._fallback(
                        current_state,
                        plan,
                        plans=plans,
                        error_code=tool_result.error_code or "TOOL_EXECUTION_FAILED",
                        message=build_tool_failure_message(
                            policy=failure_policy,
                            tool_result=tool_result,
                            tool_name=plan.tool_name,
                        ),
                    )
                continue

            if plan.action == AgentPlanAction.RESPOND_DIRECTLY:
                if current_state.status != AgentStatus.COMPLETED:
                    current_state = mark_completed(current_state, message=plan.reason)
                output = _build_loop_output(current_state)
                output_guardrail = check_output_guardrail(
                    state=current_state,
                    output=output,
                    message=plan.reason,
                )
                self._record_guardrail_event(current_state, output_guardrail)
                if not output_guardrail.allowed:
                    return self._fallback(
                        current_state,
                        plan,
                        plans=plans,
                        error_code=output_guardrail.error_code or "OUTPUT_GUARDRAIL_BLOCKED",
                        message=output_guardrail.reason,
                        allow_legacy_fallback=False,
                        guardrail_result=output_guardrail,
                    )
                log_agent_event(
                    logging.INFO,
                    "agent loop completed",
                    event="final_response",
                    state=current_state,
                    plan_action=plan.action.value,
                    metadata={"tool_results": list(current_state.tool_results.keys())},
                )
                return AgentLoopResult(
                    success=True,
                    final_state=current_state,
                    message="agent loop completed",
                    output=output,
                    last_plan=plan,
                    plans=plans,
                )

            if plan.action == AgentPlanAction.FALLBACK:
                return self._fallback(
                    current_state,
                    plan,
                    plans=plans,
                    error_code="AGENT_PLAN_FALLBACK",
                    message=plan.reason,
                )

        return self._fallback(
            current_state,
            plans[-1] if plans else None,
            plans=plans,
            error_code="AGENT_LOOP_MAX_ITERATIONS",
            message="agent loop exceeded max iterations",
        )

    def _record_guardrail_event(self, state: AgentState, guardrail_result: GuardrailResult) -> None:
        log_agent_event(
            logging.INFO if guardrail_result.allowed else logging.WARNING,
            "agent guardrail check",
            event="guardrail",
            state=state,
            success=guardrail_result.allowed,
            error_code=guardrail_result.error_code,
            metadata=guardrail_metadata(guardrail_result),
        )
        try:
            record_trace_event(
                build_trace_event(
                    trace_id=state.trace_id,
                    run_id=state.run_id,
                    user_id=state.user_id,
                    session_id=state.session_id,
                    event_type=TraceEventType.STATE_UPDATE if guardrail_result.allowed else TraceEventType.ERROR,
                    step_index=state.round_index,
                    status_before=state.status.value,
                    status_after=state.status.value if guardrail_result.allowed else AgentStatus.FAILED.value,
                    error_code=guardrail_result.error_code,
                    message=guardrail_result.reason,
                    metadata={"source": "agent_guardrail", **guardrail_metadata(guardrail_result)},
                )
            )
        except Exception:
            return

    def _fallback(
        self,
        state: AgentState,
        plan: AgentPlan | None,
        *,
        plans: list[AgentPlan],
        error_code: str,
        message: str,
        allow_legacy_fallback: bool = True,
        guardrail_result: GuardrailResult | None = None,
    ) -> AgentLoopResult:
        failed_state = state if state.status == AgentStatus.FAILED else mark_failed(
            state,
            error_code=error_code,
            message=message,
        )
        failure_policy = _latest_failure_policy(failed_state)
        fallback_result = self.fallback_handler(failed_state, plan) if self.fallback_handler and allow_legacy_fallback else None
        fallback_message = message or build_tool_failure_message(
            policy=failure_policy,
            tool_result=next(reversed(failed_state.tool_results.values())) if failed_state.tool_results else None,
            tool_name=plan.tool_name if plan else None,
        )
        log_agent_event(
            logging.WARNING,
            "agent loop fallback",
            event="fallback",
            state=failed_state,
            plan_action=plan.action.value if plan else None,
            error_code=error_code,
            metadata={
                "fallback_used": fallback_result is not None,
                "allow_legacy_fallback": allow_legacy_fallback,
                **failure_policy_metadata(failure_policy),
            },
        )
        return AgentLoopResult(
            success=False,
            final_state=failed_state,
            message=fallback_message,
            output=build_agent_fallback_output(
                state=failed_state,
                message=fallback_message,
                policy=failure_policy,
                tool_name=plan.tool_name if plan else None,
                fallback_used=fallback_result is not None,
                guardrail_result=guardrail_result,
            ),
            fallback_used=fallback_result is not None,
            fallback_result=fallback_result,
            last_plan=plan,
            plans=plans,
        )


def _build_loop_output(state: AgentState) -> dict[str, Any]:
    return {
        "intent": state.current_intent,
        "tool_results": {
            tool_name: result.model_dump(mode="json")
            for tool_name, result in state.tool_results.items()
        },
        "errors": state.errors,
        "trace_id": state.trace_id,
        "run_id": state.run_id,
    }


def _latest_failure_policy(state: AgentState):
    if not state.tool_results:
        return None
    latest_result = next(reversed(state.tool_results.values()))
    return classify_tool_failure(latest_result)
