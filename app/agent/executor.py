from collections.abc import Callable
import logging
from time import perf_counter

from app.agent.logging import log_agent_event
from app.agent.state import AgentState, AgentStatus
from app.agent.tools import ToolExecutionContext, ToolRegistry, ToolResult, default_tool_registry
from app.agent.trace import TraceEvent, TraceEventType, build_trace_event
from app.services.agent_trace import record_trace_event


TraceRecorder = Callable[[TraceEvent], int]


class ToolExecutor:
    def __init__(
        self,
        *,
        tool_registry: ToolRegistry = default_tool_registry,
        trace_recorder: TraceRecorder | None = record_trace_event,
    ) -> None:
        self.tool_registry = tool_registry
        self.trace_recorder = trace_recorder

    def execute(
        self,
        *,
        tool_name: str,
        tool_input: dict[str, object],
        state: AgentState,
        context: ToolExecutionContext,
    ) -> ToolResult:
        step_index = state.round_index
        log_agent_event(
            logging.INFO,
            "agent tool call",
            event="tool_call",
            state=state,
            tool_name=tool_name,
            raw_payload=tool_input,
            metadata=_tool_metadata(self.tool_registry, tool_name),
        )
        self._record_event(
            build_trace_event(
                trace_id=state.trace_id,
                run_id=state.run_id,
                user_id=context.user_id or state.user_id,
                session_id=state.session_id,
                event_type=TraceEventType.TOOL_CALL,
                step_index=step_index,
                status_before=state.status.value,
                status_after=state.status.value,
                tool_name=tool_name,
                input_payload=tool_input,
                metadata=_tool_metadata(self.tool_registry, tool_name),
            )
        )

        start_time = perf_counter()
        result = self.tool_registry.call(tool_name, tool_input, context=context)
        latency_ms = max(round((perf_counter() - start_time) * 1000), 0)
        status_after = AgentStatus.TOOL_COMPLETED if result.success else AgentStatus.FAILED
        log_agent_event(
            logging.INFO if result.success else logging.WARNING,
            "agent tool result",
            event="tool_result",
            state=state,
            tool_name=tool_name,
            success=result.success,
            latency_ms=latency_ms,
            error_code=result.error_code,
            raw_payload=result,
            metadata=_tool_metadata(self.tool_registry, tool_name),
        )

        self._record_event(
            build_trace_event(
                trace_id=state.trace_id,
                run_id=state.run_id,
                user_id=context.user_id or state.user_id,
                session_id=state.session_id,
                event_type=TraceEventType.TOOL_RESULT,
                step_index=step_index,
                status_before=state.status.value,
                status_after=status_after.value,
                tool_name=tool_name,
                latency_ms=latency_ms,
                input_payload=tool_input,
                output_payload=result,
                error_code=result.error_code,
                message=result.message,
                metadata=_tool_metadata(self.tool_registry, tool_name),
            )
        )

        if not result.success:
            log_agent_event(
                logging.ERROR,
                "agent tool error",
                event="tool_error",
                state=state,
                tool_name=tool_name,
                success=False,
                latency_ms=latency_ms,
                error_code=result.error_code,
            )
            self._record_event(
                build_trace_event(
                    trace_id=state.trace_id,
                    run_id=state.run_id,
                    user_id=context.user_id or state.user_id,
                    session_id=state.session_id,
                    event_type=TraceEventType.ERROR,
                    step_index=step_index,
                    status_before=state.status.value,
                    status_after=AgentStatus.FAILED.value,
                    tool_name=tool_name,
                    latency_ms=latency_ms,
                    input_payload=tool_input,
                    output_payload=result,
                    error_code=result.error_code,
                    message=result.message,
                    metadata={"source": "tool_executor"},
                )
            )

        return result

    def _record_event(self, event: TraceEvent) -> None:
        if self.trace_recorder is None:
            return
        try:
            self.trace_recorder(event)
        except Exception:
            return


def _tool_metadata(tool_registry: ToolRegistry, tool_name: str) -> dict[str, object]:
    try:
        spec = tool_registry.get(tool_name).spec
    except Exception:
        return {}
    return {
        "side_effect": spec.side_effect,
        "risk_level": spec.risk_level,
        "requires_auth": spec.requires_auth,
        "requires_admin": spec.requires_admin,
        "timeout_ms": spec.timeout_ms,
    }
