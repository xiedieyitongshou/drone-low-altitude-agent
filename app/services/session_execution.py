"""Reject overlapping turns for one authenticated user/session before reading context."""

import hashlib
import json
import logging
import os
from contextlib import contextmanager
from threading import Lock

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.services.run_observability import measure_stage


logger = logging.getLogger(__name__)
_registry_lock = Lock()
_local_locks = {}


def session_lock_key(user_id: str, session_id: str) -> int:
    encoded = json.dumps([user_id, session_id], ensure_ascii=False).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(encoded, digest_size=8).digest(), "big", signed=True)


@contextmanager
def session_execution_guard(*, user_id: str, session_id: str | None, db: Session | None = None):
    if not session_id:
        yield True
        return
    with _execution_guard(key=session_lock_key(user_id, session_id), local_key=(user_id, session_id), db=db) as admitted:
        yield admitted


@contextmanager
def operation_execution_guard(*, user_id: str, operation: str, key: str, db: Session):
    parts = ("operation", user_id, operation, key)
    encoded = json.dumps(parts, ensure_ascii=False).encode("utf-8")
    lock_key = int.from_bytes(hashlib.blake2b(encoded, digest_size=8).digest(), "big", signed=True)
    with _execution_guard(key=lock_key, local_key=parts, db=db) as admitted:
        yield admitted


@contextmanager
def _execution_guard(*, key: int, local_key: tuple, db: Session | None):
    bind = db.get_bind() if db is not None else None
    if bind is None and os.getenv("SESSION_MEMORY_BACKEND", "database") == "database":
        from app.db.session import engine

        bind = engine
    if bind is not None and bind.dialect.name == "postgresql":
        # Session-level locking survives the business transaction's intermediate commits.
        owned = not isinstance(bind, Connection)
        connection = bind.connect() if owned else bind
        acquired = False
        try:
            with measure_stage("session_guard"):
                acquired = bool(connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}))
            yield acquired
        finally:
            try:
                if acquired:
                    connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
            except SQLAlchemyError:
                logger.warning("Session execution lock connection ended before unlock", exc_info=True)
            finally:
                if owned:
                    connection.close()
        return

    # SQLite and TTLCache development/test deployments are process-local.
    with _registry_lock:
        entry = _local_locks.setdefault(local_key, [Lock(), 0])
        entry[1] += 1
    acquired = entry[0].acquire(blocking=False)
    try:
        yield acquired
    finally:
        if acquired:
            entry[0].release()
        with _registry_lock:
            entry[1] -= 1
            if entry[1] == 0:
                del _local_locks[local_key]
