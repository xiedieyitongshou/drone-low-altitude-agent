from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import SessionRecord, User
from app.services.auth_service import hash_password
from app.services.session_memory import (
    DatabaseSessionMemoryStore,
    TTLSessionMemoryStore,
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
