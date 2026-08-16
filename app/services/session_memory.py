import json
import os
from copy import deepcopy
from datetime import datetime, timedelta
from threading import Lock
from typing import Protocol

from cachetools import TTLCache
from sqlalchemy import select

from app.db.models import SessionRecord
from app.db.session import SessionLocal


DEFAULT_SESSION_USER_ID = "default_user"


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

    def __init__(self, *, ttl_seconds: int = 1800) -> None:
        self._ttl_seconds = ttl_seconds

    def get(self, session_id: str, *, user_id: str | None = None) -> dict[str, object] | None:
        normalized_user_id = _normalize_session_user_id(user_id)
        now = datetime.utcnow()
        with SessionLocal() as session:
            record = session.scalar(
                select(SessionRecord).where(
                    SessionRecord.user_id == normalized_user_id,
                    SessionRecord.session_id == session_id,
                )
            )
            if record is None:
                return None
            if record.expires_at is not None and record.expires_at <= now:
                session.delete(record)
                session.commit()
                return None
            return deepcopy(record.last_context)

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
        expires_at = now + timedelta(seconds=self._ttl_seconds) if self._ttl_seconds > 0 else None
        with SessionLocal() as session:
            record = session.scalar(
                select(SessionRecord).where(
                    SessionRecord.user_id == normalized_user_id,
                    SessionRecord.session_id == session_id,
                )
            )
            if record is None:
                record = SessionRecord(
                    session_id=session_id,
                    user_id=normalized_user_id,
                    title=title or _build_session_title(context),
                    last_context=deepcopy(context),
                    created_at=now,
                    updated_at=now,
                    expires_at=expires_at,
                )
                session.add(record)
            else:
                record.title = title or record.title or _build_session_title(context)
                record.last_context = deepcopy(context)
                record.updated_at = now
                record.expires_at = expires_at
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

    def __init__(self) -> None:
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
                self._store = create_session_memory_store()
            return self._store


def build_session_context(intent: str, parsed: dict[str, object]) -> dict[str, object]:
    """Keep only reusable fields for next-turn completion."""

    context = {
        "intent": intent,
        "task_type": parsed.get("task_type"),
        "date": parsed.get("date"),
        "start_time": parsed.get("start_time"),
        "end_time": parsed.get("end_time"),
        "location": parsed.get("location"),
        "locations": parsed.get("locations"),
        "scan_hours": parsed.get("scan_hours"),
        "current_task_id": parsed.get("task_id") or parsed.get("current_task_id"),
        "current_task_title": parsed.get("task_title") or parsed.get("current_task_title"),
        "last_recommended_windows": parsed.get("last_recommended_windows"),
        "selected_window_rank": parsed.get("window_rank") or parsed.get("selected_window_rank"),
    }
    return {key: value for key, value in context.items() if value not in (None, [], "")}


def create_session_memory_store() -> SessionMemoryStore:
    backend = os.getenv("SESSION_MEMORY_BACKEND", "ttlcache").strip().lower()
    ttl_seconds = int(os.getenv("SESSION_MEMORY_TTL_SECONDS", "1800"))

    if backend == "redis":
        return RedisSessionMemoryStore(
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            ttl_seconds=ttl_seconds,
            key_prefix=os.getenv("SESSION_MEMORY_REDIS_KEY_PREFIX", "drone_agent:session:"),
        )

    if backend == "database":
        return DatabaseSessionMemoryStore(ttl_seconds=ttl_seconds)

    if backend != "ttlcache":
        raise ValueError("SESSION_MEMORY_BACKEND must be ttlcache, redis, or database")

    return TTLSessionMemoryStore(
        maxsize=int(os.getenv("SESSION_MEMORY_MAXSIZE", "1024")),
        ttl_seconds=ttl_seconds,
    )


session_memory_store: SessionMemoryStore = LazySessionMemoryStore()


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
