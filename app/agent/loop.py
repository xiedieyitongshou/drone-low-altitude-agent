from collections.abc import Callable
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.agent.executor import ToolExecutor
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
                current_state = mark_needs_clarification(
                    current_state,
                    plan.missing_fields,
                    message=plan.reason,
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
                    message="agent requires clarification before tool execution",
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
                    return self._fallback(
                        current_state,
                        plan,
                        plans=plans,
                        error_code=tool_result.error_code or "TOOL_EXECUTION_FAILED",
                        message=tool_result.message or "tool execution failed",
                    )
                continue

            if plan.action == AgentPlanAction.RESPOND_DIRECTLY:
                if current_state.status != AgentStatus.COMPLETED:
                    current_state = mark_completed(current_state, message=plan.reason)
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
                    output=_build_loop_output(current_state),
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

    def _fallback(
        self,
        state: AgentState,
        plan: AgentPlan | None,
        *,
        plans: list[AgentPlan],
        error_code: str,
        message: str,
    ) -> AgentLoopResult:
        failed_state = state if state.status == AgentStatus.FAILED else mark_failed(
            state,
            error_code=error_code,
            message=message,
        )
        fallback_result = self.fallback_handler(failed_state, plan) if self.fallback_handler else None
        log_agent_event(
            logging.WARNING,
            "agent loop fallback",
            event="fallback",
            state=failed_state,
            plan_action=plan.action.value if plan else None,
            error_code=error_code,
            metadata={"fallback_used": self.fallback_handler is not None},
        )
        return AgentLoopResult(
            success=False,
            final_state=failed_state,
            message=message,
            fallback_used=self.fallback_handler is not None,
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
