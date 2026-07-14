from pydantic import BaseModel, Field

from app.schemas.assessment import CruiseAssessmentAdvice, RiskDecision
from app.schemas.recommendation import RecommendationWindow


class MultiLocationComparisonRequest(BaseModel):
    locations: list[str] = Field(..., min_length=2, description="候选地点列表，至少 2 个")
    date: str
    start_time: str
    end_time: str
    task_type: str = "cruise"
    purpose: str | None = None
    top_k: int = 3
    comparison_mode: str = "default"


class ComparedLocationResult(BaseModel):
    rank: int
    location: str
    available: bool = True
    location_id: str | None = None
    overall_decision: RiskDecision | None = None
    allow_cruise: bool | None = None
    risk_score: int | None = None
    score: float | None = None
    flyable_hour_count: int = 0
    max_continuous_flyable_hours: int = 0
    earliest_flyable_time: str | None = None
    window_quality_score: float | None = None
    best_window: RecommendationWindow | None = None
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    summary_risk_factors: list[str] = Field(default_factory=list)
    error_message: str | None = None
    advice: CruiseAssessmentAdvice | None = None


class MultiLocationComparisonResponse(BaseModel):
    request: dict[str, object]
    comparisons: list[ComparedLocationResult] = Field(default_factory=list)
    top_k_locations: list[ComparedLocationResult] = Field(default_factory=list)
    recommended_location: ComparedLocationResult | None = None
