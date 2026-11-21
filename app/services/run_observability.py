"""Request-scoped Trace collection and monotonic stage timing for the Agent."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from time import perf_counter
from typing import Any
from uuid import uuid4


@dataclass
class RunObservation:
    user_id: str
    session_id: str | None
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    run_id: str = field(default_factory=lambda: str(uuid4()))
    started: float = field(default_factory=perf_counter)
    events: list[Any] = field(default_factory=list)
    samples: list[dict[str, Any]] = field(default_factory=list)
    stack: list[dict[str, Any]] = field(default_factory=list)

    def record(self, event: Any) -> None:
        # Trace sequence and Agent state-step counters have different meanings.
        if event.step_index is not None:
            event.metadata = {**event.metadata, "agent_step": event.step_index}
        event.step_index = len(self.events) + 1
        self.events.append(event)

    def emit(self, event_type: str, **kwargs: Any) -> None:
        from app.agent.trace import build_trace_event

        self.record(build_trace_event(
            trace_id=self.trace_id, run_id=self.run_id, user_id=self.user_id,
            session_id=self.session_id, event_type=event_type, **kwargs,
        ))

    def timing_summary(self) -> dict[str, Any]:
        stages: dict[str, dict[str, float | int]] = {}
        for sample in self.samples:
            item = stages.setdefault(sample["stage"], {"calls": 0, "failures": 0, "duration_ms": 0.0, "self_ms": 0.0})
            item["calls"] += 1
            item["failures"] += int(not sample["ok"])
            item["duration_ms"] += sample["duration_ms"]
            item["self_ms"] += sample["self_ms"]
        for item in stages.values():
            for key in ("duration_ms", "self_ms"):
                item[key] = round(item[key], 3)
        return {
            "processing_ms": round((perf_counter() - self.started) * 1000, 3),
            "stages": stages,
            "scope": "agent_processing_before_conversation_and_trace_commit",
        }

    def flush(self, *, db: Any = None) -> None:
        from app.services.agent_trace import record_trace_events

        record_trace_events(self.events, db=db)


_current_run: ContextVar[RunObservation | None] = ContextVar("agent_observation", default=None)


def current_observation() -> RunObservation | None:
    return _current_run.get()


@contextmanager
def observe_run(*, user_id: str, session_id: str | None) -> Iterator[RunObservation]:
    observation = RunObservation(user_id=user_id, session_id=session_id)
    token = _current_run.set(observation)
    try:
        yield observation
    finally:
        _current_run.reset(token)


@contextmanager
def measure_stage(stage: str) -> Iterator[None]:
    observation = current_observation()
    if observation is None:
        yield
        return
    frame = {"stage": stage, "started": perf_counter(), "children": 0.0}
    parent = observation.stack[-1] if observation.stack else None
    observation.stack.append(frame)
    ok = False
    try:
        yield
        ok = True
    finally:
        elapsed = perf_counter() - frame["started"]
        observation.stack.pop()
        if parent is not None:
            parent["children"] += elapsed
        sample = {
            "stage": stage, "duration_ms": elapsed * 1000,
            "self_ms": max(elapsed - frame["children"], 0) * 1000,
            "start_offset_ms": round((frame["started"] - observation.started) * 1000, 3),
            "parent_stage": parent["stage"] if parent else None, "ok": ok,
        }
        observation.samples.append(sample)
        observation.emit("stage", latency_ms=round(sample["duration_ms"]), metadata={
            **sample, "duration_ms": round(sample["duration_ms"], 3), "self_ms": round(sample["self_ms"], 3),
        })


def timed_stage(stage: str) -> Callable:
    def decorate(function: Callable) -> Callable:
        @wraps(function)
        def measured(*args: Any, **kwargs: Any) -> Any:
            with measure_stage(stage):
                return function(*args, **kwargs)
        return measured
    return decorate


def emit_trace_event(event: Any, recorder: Callable) -> None:
    observation = current_observation()
    if observation is not None:
        observation.record(event)
    else:
        recorder(event)
