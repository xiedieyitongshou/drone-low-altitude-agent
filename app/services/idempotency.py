"""Durable operation identity; a content hash validates a key, never replaces it."""

from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256
import json
import re
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.db.models.operation_request import OperationRequest


TASK_CREATE = "task.create"
AGENT_QUERY = "agent.query"
AGENT_TASK_CREATE = "agent.task.create"
_agent_operation: ContextVar[str | None] = ContextVar("agent_operation", default=None)


class IdempotencyError(Exception):
    error_code = "IDEMPOTENCY_KEY_REUSED"


class OperationInProgressError(IdempotencyError):
    error_code = "IDEMPOTENCY_IN_PROGRESS"


def validate_idempotency_key(key: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key):
        raise ValueError("Idempotency-Key must contain 1-128 letters, digits, dots, underscores, colons or hyphens")
    return key


def claim_operation(
    *, db: Session, user_id: str, operation: str, key: str, payload: dict,
) -> OperationRequest:
    """Claim under a unique constraint, including when another worker is inserting.

    Does not commit: the caller must commit the receipt and business write together.
    The follow-up SELECT intentionally uses a new statement/snapshot after INSERT.
    """
    validate_idempotency_key(key)
    digest = sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    insert = postgresql_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    db.execute(
        insert(OperationRequest).values(
            id=uuid4().hex, user_id=user_id, operation=operation,
            idempotency_key=key, request_hash=digest, request_json=payload,
        ).on_conflict_do_nothing(index_elements=["user_id", "operation", "idempotency_key"])
    )
    record = db.scalars(select(OperationRequest).where(
        OperationRequest.user_id == user_id,
        OperationRequest.operation == operation,
        OperationRequest.idempotency_key == key,
    ).execution_options(populate_existing=True)).one()
    if record.request_hash != digest:
        raise IdempotencyError("同一操作 ID 对应的请求内容发生变化，请使用新的操作 ID。")
    return record


def find_agent_creation(*, db: Session, user_id: str, operation_id: str) -> OperationRequest | None:
    return db.scalar(select(OperationRequest).where(
        OperationRequest.user_id == user_id,
        OperationRequest.operation == AGENT_TASK_CREATE,
        OperationRequest.idempotency_key == operation_id,
    ))


def current_agent_operation_id() -> str | None:
    return _agent_operation.get()


@contextmanager
def agent_operation(operation_id: str):
    token = _agent_operation.set(operation_id)
    try:
        yield
    finally:
        _agent_operation.reset(token)
