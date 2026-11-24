"""Bring the configured database to the packaged revision before serving traffic."""

import logging
from threading import Lock

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.config import BASE_DIR
from app.db.session import engine


logger = logging.getLogger(__name__)
_migration_lock = Lock()
_POSTGRES_MIGRATION_LOCK = 583204819237641


def upgrade_database_to_head(bind: Engine | None = None) -> bool:
    """Apply pending revisions once; return False when already current.

    PostgreSQL workers share a transaction advisory lock and the same connection
    for the version check and migrations. Alembic's process-wide context is also
    protected from overlapping calls in one process.
    """
    config = Config(str(BASE_DIR / "alembic.ini"))
    config.attributes["configure_logger"] = False
    heads = set(ScriptDirectory.from_config(config).get_heads())
    with _migration_lock, (bind if bind is not None else engine).begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _POSTGRES_MIGRATION_LOCK})
        current = set(MigrationContext.configure(connection).get_current_heads())
        if current == heads:
            logger.info("Database schema is current")
            return False
        logger.info("Applying pending database migrations")
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    logger.info("Database migrations completed")
    return True
