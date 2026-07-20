from datetime import datetime

from sqlalchemy import Boolean, DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    default_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_task_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    default_start_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    default_end_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    output_style: Mapped[str | None] = mapped_column(String(64), nullable=True)
    common_locations_json: Mapped[list] = mapped_column(JSON, default=list)
    common_task_types_json: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ConversationRecord(Base):
    __tablename__ = "conversation_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    query: Mapped[str] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    target_endpoint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parser_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parsed_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    context_used: Mapped[bool] = mapped_column(Boolean, default=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
