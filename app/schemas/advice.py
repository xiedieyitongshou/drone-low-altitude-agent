from enum import StrEnum

from pydantic import BaseModel, Field


class AdviceCategory(StrEnum):
    RISK_ADVICE = "risk_advice"
    WARNING_ADVICE = "warning_advice"
    TASK_ADVICE = "task_advice"
    EXECUTION_ADVICE = "execution_advice"


class AdvicePriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AdviceActionType(StrEnum):
    DELAY = "delay"
    RESCHEDULE = "reschedule"
    CHANGE_TASK = "change_task"
    PREPARE_EQUIPMENT = "prepare_equipment"
    REDUCE_RISK = "reduce_risk"
    CANCEL = "cancel"


class KnowledgeAdviceItem(BaseModel):
    id: str
    category: AdviceCategory
    risk_type: list[str] = Field(default_factory=list)
    task_type: list[str] = Field(default_factory=list)
    warning_type: list[str] = Field(default_factory=list)
    warning_level: list[str] = Field(default_factory=list)
    decision_scope: list[str] = Field(default_factory=list)
    title: str
    advice_text: str
    priority: AdvicePriority
    action_type: AdviceActionType | None = None
    keywords: list[str] = Field(default_factory=list)
    source: str | None = None
    source_url: str | None = None
    notes: str | None = None


class KnowledgeAdviceLibrary(BaseModel):
    version: str
    items: list[KnowledgeAdviceItem] = Field(default_factory=list)


class AdviceRetrievalContext(BaseModel):
    task_type: str
    overall_decision: str | None = None
    risk_tags: list[str] = Field(default_factory=list)
    warning_types: list[str] = Field(default_factory=list)
    warning_levels: list[str] = Field(default_factory=list)
    limit: int = 5


class AdviceSuggestion(BaseModel):
    id: str
    title: str
    advice_text: str
    priority: AdvicePriority
    action_type: AdviceActionType | None = None
    source: str | None = None
    source_url: str | None = None
    matched_by: list[str] = Field(default_factory=list)


class RetrievedKnowledgeSnippet(BaseModel):
    id: str
    title: str
    content: str
    score: float
    source: str | None = None
    source_url: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class KnowledgeRetrievalRequest(BaseModel):
    task_type: str
    overall_decision: str | None = None
    risk_reasons: list[str] = Field(default_factory=list)
    warning_types: list[str] = Field(default_factory=list)
    warning_levels: list[str] = Field(default_factory=list)
    top_k: int = 5


class KnowledgeRetrievalResponse(BaseModel):
    context: AdviceRetrievalContext
    snippets: list[RetrievedKnowledgeSnippet] = Field(default_factory=list)
    advice: list[AdviceSuggestion] = Field(default_factory=list)
