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


_SESSION_TTL_SECONDS = int(os.getenv("SESSION_MEMORY_TTL_SECONDS", "1800"))
_SESSION_MAXSIZE = int(os.getenv("SESSION_MEMORY_MAXSIZE", "1024"))
session_memory_store: SessionMemoryStore = TTLSessionMemoryStore(
    maxsize=_SESSION_MAXSIZE,
    ttl_seconds=_SESSION_TTL_SECONDS,
)
