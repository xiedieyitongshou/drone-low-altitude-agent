from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(255), index=True)
    content: Mapped[str] = mapped_column(Text)
    knowledge_type: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)

    region: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    province: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    task_types_json: Mapped[list] = mapped_column(JSON, default=list)
    risk_tags_json: Mapped[list] = mapped_column(JSON, default=list)
    warning_types_json: Mapped[list] = mapped_column(JSON, default=list)
    warning_levels_json: Mapped[list] = mapped_column(JSON, default=list)
    decision_scopes_json: Mapped[list] = mapped_column(JSON, default=list)
    keywords_json: Mapped[list] = mapped_column(JSON, default=list)

    visibility: Mapped[str] = mapped_column(String(32), default="public", index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), default="public", index=True)
    user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id"), index=True, nullable=True)
    version: Mapped[str] = mapped_column(String(32), default="v1", index=True)

    review_status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    index_dirty: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime, index=True, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, index=True, nullable=True)

    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KnowledgeIndexJob(Base):
    __tablename__ = "knowledge_index_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    index_type: Mapped[str] = mapped_column(String(32), default="hybrid", index=True)
    triggered_by_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id"), index=True, nullable=True)
    document_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
