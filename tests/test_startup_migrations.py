import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import Mock

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, inspect, text

from app.core.config import BASE_DIR
from app.db.migrations import upgrade_database_to_head
from app.db.models import User
from main import app


@pytest.fixture
def migration_engine(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'startup.db').as_posix()}")
    try:
        yield engine
    finally:
        engine.dispose()


async def idle_cleanup():
    await asyncio.sleep(3600)


def test_fresh_database_updates_once_and_preserves_existing_rows(migration_engine, monkeypatch):
    assert upgrade_database_to_head(migration_engine) is True
    with migration_engine.begin() as connection:
        connection.execute(User.__table__.insert().values(id="existing", username="existing", password_hash="UNUSABLE_PASSWORD"))
    upgrade = Mock(side_effect=AssertionError("a current database must not rerun migrations"))
    monkeypatch.setattr("app.db.migrations.command.upgrade", upgrade)
    assert upgrade_database_to_head(migration_engine) is False
    upgrade.assert_not_called()
    with migration_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM users WHERE id='existing'")) == 1
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "d8a4c6e1f025"
        assert inspect(connection).has_table("operation_requests")


def test_existing_database_receives_pending_revision(migration_engine):
    config = Config(str(BASE_DIR / "alembic.ini"))
    config.attributes["configure_logger"] = False
    with migration_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "c6a2f41d8e90")
    assert not inspect(migration_engine).has_table("operation_requests")
    assert upgrade_database_to_head(migration_engine) is True
    assert inspect(migration_engine).has_table("operation_requests")


def test_overlapping_local_startups_apply_migrations_once(migration_engine):
    barrier = Barrier(2)

    def start():
        barrier.wait(timeout=10)
        return upgrade_database_to_head(migration_engine)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: start(), range(2)))
    assert sorted(results) == [False, True]


def test_app_startup_updates_schema_before_serving(migration_engine, monkeypatch):
    monkeypatch.setenv("AUTO_MIGRATE_ON_STARTUP", "true")
    migration = Mock(side_effect=lambda: upgrade_database_to_head(migration_engine))
    monkeypatch.setattr("main.upgrade_database_to_head", migration)
    monkeypatch.setattr("main.run_database_session_cleanup", idle_cleanup)
    with TestClient(app) as client:
        assert inspect(migration_engine).has_table("operation_requests")
        assert client.get("/health").status_code == 200
    migration.assert_called_once_with()


def test_app_startup_stops_if_migration_fails(monkeypatch):
    monkeypatch.setenv("AUTO_MIGRATE_ON_STARTUP", "true")
    monkeypatch.setattr("main.upgrade_database_to_head", Mock(side_effect=RuntimeError("injected migration failure")))
    cleanup = Mock()
    monkeypatch.setattr("main.run_database_session_cleanup", cleanup)
    with pytest.raises(RuntimeError, match="injected migration failure"):
        with TestClient(app):
            raise AssertionError("the app must not become ready")
    cleanup.assert_not_called()


def test_separately_managed_migrations_can_disable_startup_check(monkeypatch):
    monkeypatch.setenv("AUTO_MIGRATE_ON_STARTUP", "false")
    migration = Mock(side_effect=AssertionError("disabled"))
    monkeypatch.setattr("main.upgrade_database_to_head", migration)
    monkeypatch.setattr("main.run_database_session_cleanup", idle_cleanup)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
    migration.assert_not_called()
