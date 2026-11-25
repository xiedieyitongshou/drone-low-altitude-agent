"""Shared deadlines and bounded execution for one Agent request.

Timing out revokes permission to start another write. It cannot undo a COMMIT
already in progress; durable operation receipts remain the source of recovery.
Running Python threads are not killed and retain their capacity slot until exit.
"""

import os
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, wait
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from dataclasses import dataclass, field
from threading import BoundedSemaphore, Event, Lock
from time import monotonic
from typing import TypeVar
from uuid import uuid4

from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session


T = TypeVar("T")


class ExecutionTimeout(TimeoutError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class ExecutionCapacityError(RuntimeError):
    error_code = "EXECUTION_CAPACITY_EXCEEDED"


@dataclass
class ExecutionBudget:
    deadline: float
    error_code: str = "REQUEST_DEADLINE_EXCEEDED"
    parent: "ExecutionBudget | None" = None
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    run_id: str = field(default_factory=lambda: str(uuid4()))
    _cancelled: Event = field(default_factory=Event, repr=False)
    _lock: Lock = field(default_factory=Lock, repr=False)

    @classmethod
    def start(cls, timeout_ms: float, *, parent: "ExecutionBudget | None" = None,
              error_code: str = "REQUEST_DEADLINE_EXCEEDED") -> "ExecutionBudget":
        deadline = monotonic() + max(timeout_ms, 0) / 1000
        if parent is not None:
            deadline = min(deadline, parent.deadline)
        return cls(deadline=deadline, parent=parent, error_code=error_code,
                   **({"trace_id": parent.trace_id, "run_id": parent.run_id} if parent else {}))

    def check(self) -> None:
        if self.parent is not None:
            self.parent.check()
        with self._lock:
            if self._cancelled.is_set() or monotonic() >= self.deadline:
                self._cancelled.set()
                raise ExecutionTimeout(self.error_code, self.message)

    @property
    def message(self) -> str:
        if self.error_code == "TOOL_TIMEOUT":
            return "工具调用超时，请沿用原操作 ID 重试以确认结果。"
        return "本次请求已超过时间预算，请沿用原操作 ID 重试以确认结果。"

    def remaining_seconds(self) -> float:
        self.check()
        return max(self.deadline - monotonic(), 0)

    def cancel(self) -> None:
        with self._lock:
            self._cancelled.set()


_current_budget: ContextVar[ExecutionBudget | None] = ContextVar("execution_budget", default=None)


def current_budget() -> ExecutionBudget | None:
    return _current_budget.get()


def check_execution_budget() -> None:
    budget = current_budget()
    if budget is not None:
        budget.check()


@contextmanager
def use_execution_budget(budget: ExecutionBudget) -> Iterator[None]:
    token = _current_budget.set(budget)
    try:
        budget.check()
        yield
    finally:
        _current_budget.reset(token)


def remaining_timeout(configured_seconds: float) -> float:
    budget = current_budget()
    return min(configured_seconds, budget.remaining_seconds()) if budget else configured_seconds


def budgeted_sleep(seconds: float) -> None:
    budget = current_budget()
    if budget is None:
        Event().wait(seconds)
        return
    # Poll parent cancellation too: a tool has its own cancellation event.
    until = monotonic() + seconds
    while monotonic() < until:
        remaining = budget.remaining_seconds()
        budget._cancelled.wait(min(until - monotonic(), remaining, 0.05))
    budget.check()


class BoundedExecutionPool:
    """No unbounded executor queue, including after callers have timed out."""

    def __init__(self, *, max_workers: int, name: str) -> None:
        self._slots = BoundedSemaphore(max_workers)
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix=name)

    def run(self, function: Callable[[], T], budget: ExecutionBudget) -> T:
        budget.check()
        if not self._slots.acquire(blocking=False):
            raise ExecutionCapacityError("执行资源暂时繁忙，请保留原操作 ID 稍后重试。")
        context = copy_context()

        def execute() -> T:
            with use_execution_budget(budget):
                return function()

        try:
            future = self._executor.submit(context.run, execute)
        except BaseException:
            self._slots.release()
            raise
        future.add_done_callback(lambda _: self._slots.release())
        try:
            done, _ = wait([future], timeout=budget.remaining_seconds())
            if not done:
                budget.cancel()
                future.cancel()  # Only cancels work that has not started.
                budget.check()
            budget.check()  # Never accept a result received past its deadline.
            return future.result()
        except ExecutionTimeout:
            budget.cancel()
            future.cancel()
            raise

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)


_pools: dict[str, BoundedExecutionPool] = {}
_pools_lock = Lock()


def execution_pool(kind: str) -> BoundedExecutionPool:
    # Requests wait on tools, so they must not consume the same worker pool.
    with _pools_lock:
        if kind not in _pools:
            default_workers = "2" if kind == "cleanup" else "4"
            workers = max(int(os.getenv(f"AGENT_{kind.upper()}_WORKERS", default_workers)), 1)
            _pools[kind] = BoundedExecutionPool(max_workers=workers, name=f"agent-{kind}")
        return _pools[kind]


def worker_database_bind(source: Session | None) -> Engine | None:
    """Extract immutable connection configuration on the owning thread."""
    if source is None:
        return None
    if source.new or source.dirty or source.deleted:
        raise ValueError("Agent workers require committed input data")
    bind = source.get_bind()
    if isinstance(bind, Connection):
        raise ValueError("Agent workers require an engine-bound Session, not a shared transaction connection")
    # Release read transactions before waiting on another worker/connection.
    source.rollback()
    return bind


@contextmanager
def worker_database(bind: Engine | None) -> Iterator[Session | None]:
    if bind is None:
        yield None
        return
    with Session(bind=bind, autoflush=False, expire_on_commit=True) as owned:
        yield owned


@event.listens_for(Session, "before_commit")
def _check_before_commit(session: Session) -> None:
    # This is the admission point for COMMIT, not a promise to cancel a COMMIT
    # already sent to the database. Recovery must account for acknowledgement loss.
    check_execution_budget()


@event.listens_for(Session, "before_flush")
def _check_before_flush(session: Session, flush_context, instances) -> None:
    check_execution_budget()


@event.listens_for(Session, "after_begin")
def _limit_database_waits(session: Session, transaction, connection: Connection) -> None:
    budget = current_budget()
    if budget is None:
        return
    budget.check()
    if connection.dialect.name == "postgresql":
        milliseconds = max(int(budget.remaining_seconds() * 1000), 1)
        connection.exec_driver_sql(f"SET LOCAL statement_timeout = {milliseconds}")
        connection.exec_driver_sql(f"SET LOCAL lock_timeout = {milliseconds}")
