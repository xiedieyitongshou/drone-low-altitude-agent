from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WeatherProviderSnapshot(Base):
    __tablename__ = "weather_provider_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    provider_name: Mapped[str] = mapped_column(String(32), index=True)
    snapshot_type: Mapped[str] = mapped_column(String(32), index=True)
    provider_endpoint: Mapped[str] = mapped_column(String(255))
    provider_update_time: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_payload_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WeatherHourlySnapshot(Base):
    __tablename__ = "weather_hourly_snapshots"
    __table_args__ = (
        Index("ix_weather_hourly_request_location_fx_time", "request_id", "location_id", "fx_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    provider_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("weather_provider_snapshots.id"),
        nullable=True,
    )
    update_time: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fx_time: Mapped[str] = mapped_column(String(64), index=True)
    temp: Mapped[str | None] = mapped_column(String(32), nullable=True)
    text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    wind_scale: Mapped[str | None] = mapped_column(String(32), nullable=True)
    wind_speed: Mapped[str | None] = mapped_column(String(32), nullable=True)
    humidity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    precip: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pop: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pressure: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cloud: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WeatherWarningSnapshot(Base):
    __tablename__ = "weather_warning_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    provider_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("weather_provider_snapshots.id"),
        nullable=True,
    )
    warning_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    warning_level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sender: Mapped[str | None] = mapped_column(String(128), nullable=True)
    publish_time: Mapped[str | None] = mapped_column(String(64), nullable=True)
    start_time: Mapped[str | None] = mapped_column(String(64), nullable=True)
    end_time: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    text: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
