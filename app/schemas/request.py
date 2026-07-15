from datetime import date, datetime, time, timedelta

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.rules.mission_profiles import is_supported_task_type, normalize_task_type


class CruiseEvaluateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    location: str = Field(..., description="任务地点，例如：深圳湾")
    date: str = Field(..., description="任务日期，格式：YYYY-MM-DD")
    start_time: str = Field(..., description="开始时间，格式：HH:MM")
    end_time: str = Field(..., description="结束时间，格式：HH:MM，可传 24:00")
    task_type: str = Field(default="cruise", description="任务类型，例如：cruise / inspection")
    purpose: str | None = Field(default=None, description="任务目的或补充说明")
    normalized_date: str | None = None
    normalized_start_time: str | None = None
    normalized_end_time: str | None = None
    spans_next_day: bool = False
    start_datetime: str | None = None
    end_datetime: str | None = None

    @field_validator("date")
    @classmethod
    def validate_date_format(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("date must use YYYY-MM-DD format") from exc
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, value: str) -> str:
        if value == "24:00":
            return value
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError as exc:
            raise ValueError("time must use HH:MM format") from exc
        return value

    @field_validator("task_type")
    @classmethod
    def validate_task_type(cls, value: str) -> str:
        normalized = normalize_task_type(value)
        if not is_supported_task_type(normalized):
            raise ValueError("task_type must be one of: cruise, inspection, hover, survey")
        return normalized

    @model_validator(mode="after")
    def normalize_time_range(self) -> "CruiseEvaluateRequest":
        if self.start_time == "24:00":
            raise ValueError("start_time cannot be 24:00")

        base_date = date.fromisoformat(self.date)
        start_clock = datetime.strptime(self.start_time, "%H:%M").time()
        end_clock = time(0, 0) if self.end_time == "24:00" else datetime.strptime(self.end_time, "%H:%M").time()

        start_dt = datetime.combine(base_date, start_clock)
        end_dt = datetime.combine(base_date, end_clock)
        spans_next_day = False

        if self.end_time == "24:00":
            end_dt = datetime.combine(base_date + timedelta(days=1), time(0, 0))
            spans_next_day = True
        elif end_dt <= start_dt:
            end_dt = datetime.combine(base_date + timedelta(days=1), end_clock)
            spans_next_day = True

        if end_dt <= start_dt:
            raise ValueError("end_time must be later than start_time")

        self.normalized_date = base_date.isoformat()
        self.normalized_start_time = start_dt.strftime("%H:%M")
        self.normalized_end_time = "24:00" if self.end_time == "24:00" else end_clock.strftime("%H:%M")
        self.spans_next_day = spans_next_day
        self.start_datetime = start_dt.isoformat()
        self.end_datetime = end_dt.isoformat()
        return self
