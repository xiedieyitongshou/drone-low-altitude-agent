import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import ConversationRecord, SessionRecord, User
from app.services.auth_service import hash_password
from app.services.session_memory import (
    DatabaseSessionMemoryStore,
    LazySessionMemoryStore,
    TTLSessionMemoryStore,
    create_anonymous_session_memory_store,
    create_session_memory_store,
)


def build_session_local() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        db.add_all(
            [
                User(
                    id="user-a",
                    username="user_a",
                    password_hash=hash_password("demo123456"),
                    role="user",
                    is_active=True,
                ),
                User(
                    id="user-b",
                    username="user_b",
                    password_hash=hash_password("demo123456"),
                    role="user",
                    is_active=True,
                ),
            ]
        )
        db.commit()
    return SessionLocal


def test_ttl_session_memory_is_scoped_by_user_id() -> None:
    store = TTLSessionMemoryStore()

    store.set("same-session", {"location": "深圳"}, user_id="user-a")
    store.set("same-session", {"location": "广州"}, user_id="user-b")

    assert store.get("same-session", user_id="user-a") == {"location": "深圳"}
    assert store.get("same-session", user_id="user-b") == {"location": "广州"}


def test_database_session_memory_persists_context_by_user_and_session() -> None:
    SessionLocal = build_session_local()
    store = DatabaseSessionMemoryStore(ttl_seconds=1800)

    with patch("app.services.session_memory.SessionLocal", SessionLocal):
        store.set("same-session", {"location": "深圳"}, user_id="user-a", title="深圳任务")
        store.set("same-session", {"location": "广州"}, user_id="user-b", title="广州任务")

        assert store.get("same-session", user_id="user-a") == {"location": "深圳"}
        assert store.get("same-session", user_id="user-b") == {"location": "广州"}

        with SessionLocal() as db:
            records = db.scalars(select(SessionRecord).order_by(SessionRecord.user_id.asc())).all()
            assert len(records) == 2
            assert [(item.user_id, item.session_id, item.title) for item in records] == [
                ("user-a", "same-session", "深圳任务"),
                ("user-b", "same-session", "广州任务"),
            ]


def test_database_session_memory_removes_expired_context() -> None:
    SessionLocal = build_session_local()
    store = DatabaseSessionMemoryStore(ttl_seconds=1800)

    with patch("app.services.session_memory.SessionLocal", SessionLocal):
        with SessionLocal() as db:
            db.add(
                SessionRecord(
                    session_id="expired-session",
                    user_id="user-a",
                    title="expired",
                    last_context={"location": "深圳"},
                    created_at=datetime.utcnow() - timedelta(hours=2),
                    updated_at=datetime.utcnow() - timedelta(hours=2),
                    expires_at=datetime.utcnow() - timedelta(seconds=1),
                )
            )
            db.commit()

        assert store.get("expired-session", user_id="user-a") is None

        with SessionLocal() as db:
            assert db.scalar(select(SessionRecord).where(SessionRecord.session_id == "expired-session")) is None


def test_session_memory_factory_supports_database_backend() -> None:
    with patch.dict("os.environ", {"SESSION_MEMORY_BACKEND": "database"}, clear=False):
        assert isinstance(create_session_memory_store(), DatabaseSessionMemoryStore)


def test_default_database_sessions_restore_latest_context_by_user(
    api_session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SESSION_MEMORY_BACKEND", raising=False)
    monkeypatch.delenv("SESSION_MEMORY_TTL_SECONDS", raising=False)
    monkeypatch.setattr("app.services.session_memory.SessionLocal", api_session_factory)
    with api_session_factory.begin() as db:
        db.add_all(
            [
                User(id="session-owner", username="session-owner", password_hash="UNUSABLE_PASSWORD"),
                User(id="session-other", username="session-other", password_hash="UNUSABLE_PASSWORD"),
            ]
        )

    store = create_session_memory_store()
    store.set("shared", {"location": "深圳"}, user_id="session-owner", title="原任务")
    store.set("shared", {"location": "深圳湾"}, user_id="session-owner")

    restored = create_session_memory_store()
    assert restored.get("shared", user_id="session-owner") == {"location": "深圳湾"}
    assert restored.get("shared", user_id="session-other") is None

    with api_session_factory() as db:
        owner_record = db.scalars(select(SessionRecord).where(SessionRecord.session_id == "shared")).one()
        assert owner_record.title == "原任务"
        assert owner_record.expires_at == owner_record.updated_at + timedelta(days=30)


def test_session_cleanup_checks_last_write_and_keeps_chat_history(
    api_session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.session_memory.SessionLocal", api_session_factory)
    now = datetime.utcnow()
    with api_session_factory.begin() as db:
        db.add(User(id="cleanup-owner", username="cleanup-owner", password_hash="UNUSABLE_PASSWORD"))
        db.flush()
        for session_id, updated_days_ago in [("old-read", 31), ("old-unread", 31), ("recent-write", 29)]:
            db.add(
                SessionRecord(
                    session_id=session_id,
                    user_id="cleanup-owner",
                    last_context={"location": "深圳"},
                    created_at=now - timedelta(days=45),
                    updated_at=now - timedelta(days=updated_days_ago),
                )
            )
        db.add(
            ConversationRecord(
                conversation_id="kept-history",
                session_id="old-unread",
                user_id="cleanup-owner",
                query="深圳巡检",
            )
        )

    store = DatabaseSessionMemoryStore()
    assert store.get("old-read", user_id="cleanup-owner") is None
    assert store.delete_expired() == 1
    assert store.delete_expired() == 0
    assert store.get("recent-write", user_id="cleanup-owner") == {"location": "深圳"}
    with api_session_factory() as db:
        history = db.scalar(select(ConversationRecord).where(ConversationRecord.conversation_id == "kept-history"))
        assert history is not None
        assert history.session_id == "old-unread"


def test_public_parser_uses_redis_with_its_own_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    from main import app

    monkeypatch.setenv("NL_PARSER_MODE", "rule")
    monkeypatch.setenv("SESSION_MEMORY_TTL_SECONDS", "2592000")
    monkeypatch.delenv("ANONYMOUS_SESSION_TTL_SECONDS", raising=False)
    monkeypatch.delenv("SESSION_MEMORY_REDIS_KEY_PREFIX", raising=False)
    monkeypatch.setattr("main.anonymous_session_memory_store", LazySessionMemoryStore(create_anonymous_session_memory_store))

    with patch("redis.Redis.from_url") as from_url:
        redis = from_url.return_value
        client = TestClient(app)
        query = "明天下午在深圳湾巡检"
        response = client.post("/nl/parse", json={"query": query})
        assert response.status_code == 200
        from_url.assert_not_called()

        key = "drone_agent:session:anonymous:default_user:parse-session"
        redis.get.return_value = None
        response = client.post("/nl/parse", json={"session_id": "parse-session", "query": query})
        assert response.status_code == 200
        written_key, ttl, context = redis.setex.call_args.args
        assert (written_key, ttl) == (key, 1800)
        assert json.loads(context)["location"] == "深圳湾"

        redis.get.return_value = context
        response = client.post("/nl/parse", json={"session_id": "parse-session", "query": "后天呢"})
        assert response.status_code == 200
        assert response.json()["context_used"]
        assert response.json()["parsed"]["location"] == "深圳湾"
        assert redis.setex.call_args.args[:2] == (key, 1800)
