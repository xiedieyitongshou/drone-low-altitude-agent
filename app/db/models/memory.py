from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), unique=True, index=True)
    default_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_task_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    default_start_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    default_end_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    output_style: Mapped[str | None] = mapped_column(String(64), nullable=True)
    common_locations_json: Mapped[list] = mapped_column(JSON, default=list)
    common_task_types_json: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="profile")


class ConversationRecord(Base):
    __tablename__ = "conversation_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), index=True)
    task_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("mission_tasks.id"), index=True, nullable=True)
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

    user: Mapped["User"] = relationship(back_populates="conversations")
    mission_task: Mapped["MissionTask | None"] = relationship(back_populates="conversations")


class SessionRecord(Base):
    __tablename__ = "session_records"
    __table_args__ = (
        UniqueConstraint("user_id", "session_id", name="uq_session_records_user_session"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_context: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="sessions")
