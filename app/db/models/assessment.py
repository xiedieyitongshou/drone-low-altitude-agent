from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CruiseAssessment(Base):
    __tablename__ = "cruise_assessments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    task_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("mission_tasks.id"), index=True, nullable=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    allow_cruise: Mapped[bool] = mapped_column(Boolean)
    overall_decision: Mapped[str] = mapped_column(String(32), index=True)
    summary_risk_factors_json: Mapped[list] = mapped_column(JSON)
    rule_set_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    rule_set_version: Mapped[int | None] = mapped_column(nullable=True)
    rule_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    rule_hits_json: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CruiseHourlyAssessment(Base):
    __tablename__ = "cruise_hourly_assessments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("cruise_assessments.id"), index=True)
    fx_time: Mapped[str] = mapped_column(String(64), index=True)
    decision: Mapped[str] = mapped_column(String(32), index=True)
    risk_factors_json: Mapped[list] = mapped_column(JSON)
    rule_hits_json: Mapped[list] = mapped_column(JSON, default=list)
    weather_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("weather_hourly_snapshots.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
