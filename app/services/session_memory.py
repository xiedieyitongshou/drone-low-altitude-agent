import asyncio
import json
import logging
import os
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timedelta
from threading import Lock
from typing import Protocol

from cachetools import TTLCache
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import SessionRecord
from app.db.session import SessionLocal


DEFAULT_SESSION_USER_ID = "default_user"
DEFAULT_SESSION_TTL_SECONDS = 1800
DEFAULT_DATABASE_SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
SESSION_CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60
logger = logging.getLogger(__name__)


class SessionMemoryStore(Protocol):
    """Abstract session memory contract."""

    def get(self, session_id: str, *, user_id: str | None = None) -> dict[str, object] | None: ...

    def set(
        self,
        session_id: str,
        context: dict[str, object],
        *,
        user_id: str | None = None,
        title: str | None = None,
    ) -> None: ...

    def delete(self, session_id: str, *, user_id: str | None = None) -> None: ...


class TTLSessionMemoryStore:
    """In-process session memory for short-lived conversational context."""

    def __init__(self, *, maxsize: int = 1024, ttl_seconds: int = 1800) -> None:
        self._cache: TTLCache[str, dict[str, object]] = TTLCache(maxsize=maxsize, ttl=ttl_seconds)
        self._lock = Lock()

    def get(self, session_id: str, *, user_id: str | None = None) -> dict[str, object] | None:
        with self._lock:
            value = self._cache.get(_scoped_session_key(session_id, user_id))
            return deepcopy(value) if value is not None else None

    def set(
        self,
        session_id: str,
        context: dict[str, object],
        *,
        user_id: str | None = None,
        title: str | None = None,
    ) -> None:
        with self._lock:
            self._cache[_scoped_session_key(session_id, user_id)] = deepcopy(context)

    def delete(self, session_id: str, *, user_id: str | None = None) -> None:
        with self._lock:
            self._cache.pop(_scoped_session_key(session_id, user_id), None)


class RedisSessionMemoryStore:
    """Redis-backed session memory for shared deployment environments."""

    def __init__(
        self,
        *,
        redis_url: str,
        ttl_seconds: int = 1800,
        key_prefix: str = "drone_agent:session:",
    ) -> None:
        from redis import Redis

        self._client = Redis.from_url(redis_url, decode_responses=True)
        self._client.ping()
        self._ttl_seconds = ttl_seconds
        self._key_prefix = key_prefix

    def get(self, session_id: str, *, user_id: str | None = None) -> dict[str, object] | None:
        raw_value = self._client.get(self._key(session_id, user_id))
        if raw_value is None:
            return None
        value = json.loads(raw_value)
        return value if isinstance(value, dict) else None

    def set(
        self,
        session_id: str,
        context: dict[str, object],
        *,
        user_id: str | None = None,
        title: str | None = None,
    ) -> None:
        self._client.setex(
            self._key(session_id, user_id),
            self._ttl_seconds,
            json.dumps(context, ensure_ascii=False),
        )

    def delete(self, session_id: str, *, user_id: str | None = None) -> None:
        self._client.delete(self._key(session_id, user_id))

    def _key(self, session_id: str, user_id: str | None) -> str:
        return f"{self._key_prefix}{_scoped_session_key(session_id, user_id)}"


class DatabaseSessionMemoryStore:
    """Database-backed session memory for durable conversation context."""

    def __init__(self, *, ttl_seconds: int = DEFAULT_DATABASE_SESSION_TTL_SECONDS) -> None:
        self._ttl_seconds = ttl_seconds

    def get(self, session_id: str, *, user_id: str | None = None) -> dict[str, object] | None:
        normalized_user_id = _normalize_session_user_id(user_id)
        now = datetime.utcnow()
        expired = self._is_expired(now)
        with SessionLocal() as session:
            result = session.execute(
                select(SessionRecord, expired).where(
                    SessionRecord.user_id == normalized_user_id,
                    SessionRecord.session_id == session_id,
                )
            ).one_or_none()
            if result is None:
                return None
            record, is_expired = result
            if is_expired:
                session.execute(
                    delete(SessionRecord).where(
                        SessionRecord.id == record.id,
                        expired,
                    )
                )
                session.commit()
                return None
            return deepcopy(record.last_context)

    def delete_expired(self) -> int:
        with SessionLocal.begin() as session:
            result = session.execute(delete(SessionRecord).where(self._is_expired(datetime.utcnow())))
            return result.rowcount

    def _is_expired(self, now: datetime) -> ColumnElement[bool]:
        expiry_passed = and_(SessionRecord.expires_at.is_not(None), SessionRecord.expires_at <= now)
        if self._ttl_seconds <= 0:
            return expiry_passed
        # Older sessions were saved without an expiry, so also check their last write.
        cutoff = now - timedelta(seconds=self._ttl_seconds)
        return or_(expiry_passed, SessionRecord.updated_at <= cutoff)

    def set(
        self,
        session_id: str,
        context: dict[str, object],
        *,
        user_id: str | None = None,
        title: str | None = None,
    ) -> None:
        normalized_user_id = _normalize_session_user_id(user_id)
        now = datetime.utcnow()
        ttl_seconds = self._ttl_seconds
        if normalized_user_id == DEFAULT_SESSION_USER_ID and ttl_seconds <= 0:
            ttl_seconds = DEFAULT_SESSION_TTL_SECONDS
        expires_at = now + timedelta(seconds=ttl_seconds) if ttl_seconds > 0 else None
        with SessionLocal() as session:
            insert = postgresql_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
            statement = insert(SessionRecord).values(
                session_id=session_id,
                user_id=normalized_user_id,
                title=title or _build_session_title(context),
                last_context=deepcopy(context),
                created_at=now,
                updated_at=now,
                expires_at=expires_at,
            )
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=[SessionRecord.user_id, SessionRecord.session_id],
                    set_={
                        "title": title or func.coalesce(func.nullif(SessionRecord.title, ""), statement.excluded.title),
                        "last_context": statement.excluded.last_context,
                        "updated_at": statement.excluded.updated_at,
                        "expires_at": statement.excluded.expires_at,
                    },
                )
            )
            session.commit()

    def delete(self, session_id: str, *, user_id: str | None = None) -> None:
        normalized_user_id = _normalize_session_user_id(user_id)
        with SessionLocal() as session:
            record = session.scalar(
                select(SessionRecord).where(
                    SessionRecord.user_id == normalized_user_id,
                    SessionRecord.session_id == session_id,
                )
            )
            if record is not None:
                session.delete(record)
                session.commit()


class LazySessionMemoryStore:
    """Create the configured backend on first use, after environment loading."""

    def __init__(self, factory: Callable[[], SessionMemoryStore]) -> None:
        self._factory = factory
        self._store: SessionMemoryStore | None = None
        self._lock = Lock()

    def get(self, session_id: str, *, user_id: str | None = None) -> dict[str, object] | None:
        return self._get_store().get(session_id, user_id=user_id)

    def set(
        self,
        session_id: str,
        context: dict[str, object],
        *,
        user_id: str | None = None,
        title: str | None = None,
    ) -> None:
        self._get_store().set(session_id, context, user_id=user_id, title=title)

    def delete(self, session_id: str, *, user_id: str | None = None) -> None:
        self._get_store().delete(session_id, user_id=user_id)

    def _get_store(self) -> SessionMemoryStore:
        if self._store is not None:
            return self._store
        with self._lock:
            if self._store is None:
                self._store = self._factory()
            return self._store


def build_session_context(
    intent: str, parsed: dict[str, object], *, knowledge_city: object = None
) -> dict[str, object]:
    """Keep only reusable fields for next-turn completion."""

    context = {
        "intent": intent,
        "task_type": parsed.get("task_type"),
        "date": parsed.get("date"),
        "start_time": parsed.get("start_time"),
        "end_time": parsed.get("end_time"),
        "city": knowledge_city,
        "scan_hours": parsed.get("scan_hours"),
        "current_task_id": parsed.get("task_id") or parsed.get("current_task_id"),
        "current_task_title": parsed.get("task_title") or parsed.get("current_task_title"),
        "last_recommended_windows": parsed.get("last_recommended_windows"),
        "selected_window_rank": parsed.get("window_rank") or parsed.get("selected_window_rank"),
    }
    if intent == "knowledge":
        context.update(flight_location=parsed.get("location"), flight_locations=parsed.get("locations"))
    else:
        context.update(location=parsed.get("location"), locations=parsed.get("locations"))
    return {key: value for key, value in context.items() if value not in (None, [], "")}


def create_session_memory_store() -> SessionMemoryStore:
    backend = _configured_session_backend()
    if backend == "database":
        return _create_database_session_memory_store()

    ttl_seconds = int(os.getenv("SESSION_MEMORY_TTL_SECONDS") or DEFAULT_SESSION_TTL_SECONDS)

    if backend == "redis":
        return RedisSessionMemoryStore(
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            ttl_seconds=ttl_seconds,
            key_prefix=os.getenv("SESSION_MEMORY_REDIS_KEY_PREFIX", "drone_agent:session:"),
        )

    if backend != "ttlcache":
        raise ValueError("SESSION_MEMORY_BACKEND must be ttlcache, redis, or database")

    return TTLSessionMemoryStore(
        maxsize=int(os.getenv("SESSION_MEMORY_MAXSIZE", "1024")),
        ttl_seconds=ttl_seconds,
    )


def _configured_session_backend() -> str:
    return os.getenv("SESSION_MEMORY_BACKEND", "database").strip().lower()


def _create_database_session_memory_store() -> DatabaseSessionMemoryStore:
    ttl_seconds = int(os.getenv("SESSION_MEMORY_TTL_SECONDS") or DEFAULT_DATABASE_SESSION_TTL_SECONDS)
    return DatabaseSessionMemoryStore(ttl_seconds=ttl_seconds)


def create_anonymous_session_memory_store() -> SessionMemoryStore:
    ttl_seconds = int(os.getenv("ANONYMOUS_SESSION_TTL_SECONDS") or DEFAULT_SESSION_TTL_SECONDS)
    return RedisSessionMemoryStore(
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        ttl_seconds=ttl_seconds,
        key_prefix=os.getenv("SESSION_MEMORY_REDIS_KEY_PREFIX", "drone_agent:session:") + "anonymous:",
    )


async def run_database_session_cleanup() -> None:
    if _configured_session_backend() != "database":
        return
    store = _create_database_session_memory_store()
    while True:
        try:
            deleted = await asyncio.to_thread(store.delete_expired)
            if deleted:
                logger.info("Deleted %d expired session records", deleted)
        except Exception:
            logger.exception("Could not delete expired session records")
        await asyncio.sleep(SESSION_CLEANUP_INTERVAL_SECONDS)


session_memory_store: SessionMemoryStore = LazySessionMemoryStore(create_session_memory_store)
anonymous_session_memory_store: SessionMemoryStore = LazySessionMemoryStore(create_anonymous_session_memory_store)


def _normalize_session_user_id(user_id: str | None) -> str:
    value = (user_id or "").strip()
    return value or DEFAULT_SESSION_USER_ID


def _scoped_session_key(session_id: str, user_id: str | None) -> str:
    return f"{_normalize_session_user_id(user_id)}:{session_id}"


def _build_session_title(context: dict[str, object]) -> str | None:
    intent = context.get("intent")
    location = context.get("location")
    if isinstance(location, str) and location.strip():
        return f"{location.strip()} - {intent or 'session'}"
    if isinstance(intent, str) and intent.strip():
        return intent.strip()
    return None
