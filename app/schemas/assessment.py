from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.warning import WarningDataBundle
from app.schemas.weather import WeatherDataBundle


class RiskDecision(StrEnum):
    SUITABLE = "适飞"
    CAUTION = "慎飞"
    PROHIBITED = "禁飞"


class RuleHit(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    fx_time: str | None = None
    metric: str
    operator: str
    actual_value: str | float | int | None = None
    threshold: str | float | int | list[str | float | int] | None = None
    unit: str | None = None
    decision: RiskDecision
    label: str
    risk_tag: str | None = None
    source: str = "system_default"


class HourlyAssessment(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    fx_time: str
    decision: RiskDecision
    risk_factors: list[str] = Field(default_factory=list)
    rule_hits: list[RuleHit] = Field(default_factory=list)
    weather: dict[str, str | None] = Field(default_factory=dict)


class CruiseAssessmentAdvice(BaseModel):
    allow_cruise: bool
    overall_decision: RiskDecision
    summary_risk_factors: list[str] = Field(default_factory=list)
    rule_set_id: str | None = None
    rule_set_version: int | None = None
    rule_snapshot: dict[str, object] = Field(default_factory=dict)
    rule_hits: list[RuleHit] = Field(default_factory=list)
    hourly_assessment: list[HourlyAssessment] = Field(default_factory=list)


class CruiseAssessmentResponse(BaseModel):
    request: dict[str, str | bool | None]
    weather: WeatherDataBundle | None = None
    warnings: WarningDataBundle | None = None
    advice: CruiseAssessmentAdvice


class CruiseHistoryResponse(BaseModel):
    request_id: str
    created_at: str
    request: dict[str, str | bool | None]
    weather: WeatherDataBundle | None = None
    warnings: WarningDataBundle | None = None
    advice: CruiseAssessmentAdvice


class InputValidationPreviewResponse(BaseModel):
    success: bool = True
    message: str = "input validation passed"
    request: dict[str, str | bool | None]
