import json
import os
from copy import deepcopy
from threading import Lock
from typing import Protocol

from cachetools import TTLCache


class SessionMemoryStore(Protocol):
    """Abstract session memory contract."""

    def get(self, session_id: str) -> dict[str, object] | None: ...

    def set(self, session_id: str, context: dict[str, object]) -> None: ...

    def delete(self, session_id: str) -> None: ...


class TTLSessionMemoryStore:
    """In-process session memory for short-lived conversational context."""

    def __init__(self, *, maxsize: int = 1024, ttl_seconds: int = 1800) -> None:
        self._cache: TTLCache[str, dict[str, object]] = TTLCache(maxsize=maxsize, ttl=ttl_seconds)
        self._lock = Lock()

    def get(self, session_id: str) -> dict[str, object] | None:
        with self._lock:
            value = self._cache.get(session_id)
            return deepcopy(value) if value is not None else None

    def set(self, session_id: str, context: dict[str, object]) -> None:
        with self._lock:
            self._cache[session_id] = deepcopy(context)

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._cache.pop(session_id, None)


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

    def get(self, session_id: str) -> dict[str, object] | None:
        raw_value = self._client.get(self._key(session_id))
        if raw_value is None:
            return None
        value = json.loads(raw_value)
        return value if isinstance(value, dict) else None

    def set(self, session_id: str, context: dict[str, object]) -> None:
        self._client.setex(
            self._key(session_id),
            self._ttl_seconds,
            json.dumps(context, ensure_ascii=False),
        )

    def delete(self, session_id: str) -> None:
        self._client.delete(self._key(session_id))

    def _key(self, session_id: str) -> str:
        return f"{self._key_prefix}{session_id}"


class LazySessionMemoryStore:
    """Create the configured backend on first use, after environment loading."""

    def __init__(self) -> None:
        self._store: SessionMemoryStore | None = None
        self._lock = Lock()

    def get(self, session_id: str) -> dict[str, object] | None:
        return self._get_store().get(session_id)

    def set(self, session_id: str, context: dict[str, object]) -> None:
        self._get_store().set(session_id, context)

    def delete(self, session_id: str) -> None:
        self._get_store().delete(session_id)

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

    if backend != "ttlcache":
        raise ValueError("SESSION_MEMORY_BACKEND must be ttlcache or redis")

    return TTLSessionMemoryStore(
        maxsize=int(os.getenv("SESSION_MEMORY_MAXSIZE", "1024")),
        ttl_seconds=ttl_seconds,
    )


session_memory_store: SessionMemoryStore = LazySessionMemoryStore()
