import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.core.config import load_environment


DEFAULT_DATABASE_URL = "sqlite:///./data/drone_agent.db"


def get_database_url() -> str:
    load_environment()
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def create_db_engine() -> Engine:
    database_url = get_database_url()
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, future=True, connect_args=connect_args)


engine = create_db_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
