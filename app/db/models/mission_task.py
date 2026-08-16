from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MissionTask(Base):
    __tablename__ = "mission_tasks"
    __table_args__ = (
        Index("ix_mission_tasks_user_status", "user_id", "status"),
        Index("ix_mission_tasks_user_created_at", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid4().hex)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    location_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    task_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    start_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    end_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    task_type: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    candidate_locations_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    selected_window_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    latest_decision: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    latest_request_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    latest_trace_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    latest_conversation_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    profile_context_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="mission_tasks")
    conversations: Mapped[list["ConversationRecord"]] = relationship(back_populates="mission_task")
