from datetime import datetime

from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TaskRequest(Base):
    __tablename__ = "task_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    request_type: Mapped[str] = mapped_column(String(32), index=True)
    location_text: Mapped[str] = mapped_column(String(255))
    task_date: Mapped[str] = mapped_column(String(32))
    start_time: Mapped[str] = mapped_column(String(32))
    end_time: Mapped[str] = mapped_column(String(32))
    task_type: Mapped[str] = mapped_column(String(64), index=True)
    purpose: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_request_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
