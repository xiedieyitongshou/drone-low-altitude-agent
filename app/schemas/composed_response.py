from typing import Literal

from pydantic import BaseModel, Field


class ComposedRecommendationWindow(BaseModel):
    rank: int
    start_time: str
    end_time: str
    duration_hours: int
    overall_decision: str
    risk_score: int
    reasons: list[str] = Field(default_factory=list)


class ComposedLocationRanking(BaseModel):
    rank: int
    location: str
    overall_decision: str | None = None
    score: float | None = None
    flyable_hour_count: int = 0
    max_continuous_flyable_hours: int = 0
    earliest_flyable_time: str | None = None
    summary_reason: str | None = None


class ComposedHistorySummary(BaseModel):
    request_id: str
    created_at: str
    location: str | None = None
    task_type: str | None = None
    date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    overall_decision: str | None = None


class UnifiedBusinessResponse(BaseModel):
    scene: Literal['evaluate', 'recommend', 'compare', 'history']
    summary: str
    overall_decision: str | None = None
    allow_execute: bool | None = None
    risk_reasons: list[str] = Field(default_factory=list)
    recommended_windows: list[ComposedRecommendationWindow] = Field(default_factory=list)
    ranked_locations: list[ComposedLocationRanking] = Field(default_factory=list)
    history_summary: ComposedHistorySummary | None = None
    details: dict[str, object] = Field(default_factory=dict)
