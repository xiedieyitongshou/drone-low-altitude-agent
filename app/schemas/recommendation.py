from pydantic import BaseModel, Field

from app.schemas.assessment import HourlyAssessment, RiskDecision
from app.schemas.warning import WarningDataBundle
from app.schemas.weather import WeatherDataBundle


class RecommendationWindow(BaseModel):
    rank: int
    start_time: str
    end_time: str
    duration_hours: int
    overall_decision: RiskDecision
    risk_score: int = Field(..., description="风险分数，越低越优")
    reasons: list[str] = Field(default_factory=list)
    hourly_assessment: list[HourlyAssessment] = Field(default_factory=list)


class RecommendationStrategy(BaseModel):
    min_window_hours: int
    sort_rules: list[str] = Field(default_factory=list)


class RecommendationResult(BaseModel):
    strategy: RecommendationStrategy
    recommended_windows: list[RecommendationWindow] = Field(default_factory=list)
    total_candidates: int = 0


class RecommendationRequest(BaseModel):
    location: str
    date: str
    task_type: str = "cruise"
    purpose: str | None = None
    scan_hours: int = 72
    min_window_hours: int = 2


class RecommendationResponse(BaseModel):
    request: dict[str, str | int | None]
    weather: WeatherDataBundle | None = None
    warnings: WarningDataBundle | None = None
    recommendation: RecommendationResult
