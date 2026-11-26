import os
from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateSchema, DropSchema


@pytest.fixture(autouse=True)
def isolate_startup_migrations(monkeypatch: pytest.MonkeyPatch) -> None:
    # Most API tests supply their own schema/session via dependency overrides.
    # Startup migration integration tests explicitly re-enable this behavior.
    monkeypatch.setenv("AUTO_MIGRATE_ON_STARTUP", "false")


@pytest.fixture(autouse=True)
def isolate_knowledge_publications(monkeypatch, tmp_path):
    """Never publish test knowledge or maintenance controls into the live index."""
    from app.services import admin_knowledge_indexing, vector_knowledge_store
    from app.services.advice_retriever import load_advice_library

    root = tmp_path / "knowledge-index"
    source = root / "knowledge_documents_source.json"
    monkeypatch.setattr(vector_knowledge_store, "DEFAULT_INDEX_DIR", root)
    monkeypatch.setattr(vector_knowledge_store, "DEFAULT_DB_KNOWLEDGE_PATH", source)
    monkeypatch.setattr(admin_knowledge_indexing, "DEFAULT_DB_KNOWLEDGE_PATH", source)
    load_advice_library.cache_clear()
    yield
    load_advice_library.cache_clear()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--api-db",
        choices=("sqlite", "postgresql"),
        default="sqlite",
        help="Database for API regression tests using the shared session fixture.",
    )


@pytest.fixture
def api_session_factory(pytestconfig: pytest.Config) -> Generator[sessionmaker[Session], None, None]:
    from app.db.base import Base
    import app.db.models  # noqa: F401

    if pytestconfig.getoption("--api-db") == "postgresql":
        from app.db.session import engine

        if not os.getenv("DATABASE_URL") or engine.dialect.name != "postgresql":
            raise pytest.UsageError("--api-db=postgresql requires a DATABASE_URL for a PostgreSQL test database.")

        # Agent workers own independent sessions/connections and must see real
        # commits. A per-test schema isolates them without sharing a savepoint.
        schema = f"api_test_{uuid4().hex}"
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        bind = engine.execution_options(schema_translate_map={None: schema})
        try:
            Base.metadata.create_all(bind=bind)
            yield sessionmaker(bind=bind, autoflush=False)
        finally:
            with engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
        return

    sqlite_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        Base.metadata.create_all(bind=sqlite_engine)
        yield sessionmaker(bind=sqlite_engine, autoflush=False)
    finally:
        sqlite_engine.dispose()


@pytest.fixture
def api_client(
    api_session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> Generator[TestClient, None, None]:
    from app.dependencies import get_db
    from main import app

    def override_get_db() -> Generator[Session, None, None]:
        with api_session_factory() as db:
            yield db

    monkeypatch.setitem(app.dependency_overrides, get_db, override_get_db)
    with TestClient(app) as client:
        yield client
