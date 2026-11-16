import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--api-db",
        choices=("sqlite", "postgresql"),
        default="sqlite",
        help="Database for API regression tests using the shared session fixture.",
    )


@pytest.fixture
def api_session_factory(pytestconfig: pytest.Config) -> Generator[sessionmaker[Session], None, None]:
    if pytestconfig.getoption("--api-db") == "postgresql":
        from app.db.session import engine

        if not os.getenv("DATABASE_URL") or engine.dialect.name != "postgresql":
            raise pytest.UsageError("--api-db=postgresql requires a DATABASE_URL for a PostgreSQL test database.")

        # API commits release savepoints. Closing the connection rolls back the outer transaction.
        with engine.connect() as connection:
            connection.begin()
            yield sessionmaker(bind=connection, autoflush=False, join_transaction_mode="create_savepoint")
        return

    from app.db.base import Base
    import app.db.models  # noqa: F401

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
