from pydantic import BaseModel, ConfigDict


class WarningData(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    warning_id: str | None = None
    event_type: str | None = None
    warning_level: str | None = None
    title: str | None = None
    sender: str | None = None
    publish_time: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    status: str | None = None
    text: str | None = None


class WarningDataBundle(BaseModel):
    warnings: list[WarningData]
    has_warning: bool = False
    warning_count: int = 0
