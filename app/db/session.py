import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL
from sqlalchemy.orm import sessionmaker

from app.core.config import load_environment


def get_database_url() -> str:
    load_environment()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        return database_url

    return URL.create(
        "postgresql+psycopg",
        username=os.getenv("POSTGRES_USER", "drone_agent"),
        password=os.getenv("POSTGRES_PASSWORD", "change-me-postgres-password"),
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "drone_agent"),
    ).render_as_string(hide_password=False)


def create_db_engine() -> Engine:
    database_url = get_database_url()
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, future=True, connect_args=connect_args, pool_pre_ping=True)


engine = create_db_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
