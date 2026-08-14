from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Float, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RuleSet(Base):
    __tablename__ = "rule_sets"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "name", "version", name="uq_rule_sets_owner_name_version"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(128), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_type: Mapped[str] = mapped_column(String(64), default="cruise", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    visibility: Mapped[str] = mapped_column(String(32), default="private", index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id"), index=True, nullable=True)
    tenant_id: Mapped[str] = mapped_column(String(64), default="public", index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    source: Mapped[str] = mapped_column(String(32), default="user", index=True)
    validation_errors_json: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner: Mapped["User | None"] = relationship(back_populates="rule_sets")
    items: Mapped[list["RuleItem"]] = relationship(
        back_populates="rule_set",
        cascade="all, delete-orphan",
        order_by="RuleItem.priority.asc(), RuleItem.created_at.asc()",
    )


class RuleItem(Base):
    __tablename__ = "rule_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid4()))
    rule_set_id: Mapped[str] = mapped_column(String(64), ForeignKey("rule_sets.id"), index=True)
    metric: Mapped[str] = mapped_column(String(64), index=True)
    operator: Mapped[str] = mapped_column(String(16))
    threshold_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    threshold_values_json: Mapped[list] = mapped_column(JSON, default=list)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decision: Mapped[str] = mapped_column(String(32), index=True)
    label: Mapped[str] = mapped_column(String(255))
    risk_tag: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=100, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    rule_set: Mapped["RuleSet"] = relationship(back_populates="items")
