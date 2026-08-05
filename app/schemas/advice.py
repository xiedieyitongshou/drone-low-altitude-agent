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


class KnowledgeType(StrEnum):
    RISK_ADVICE = "risk_advice"
    SOP = "sop"
    POLICY_HINT = "policy_hint"
    FAQ = "faq"


class KnowledgeVisibility(StrEnum):
    PUBLIC = "public"
    TENANT = "tenant"
    PRIVATE = "private"


class KnowledgeReviewStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    EXPIRED = "expired"


class KnowledgeAdviceItem(BaseModel):
    id: str
    category: AdviceCategory
    knowledge_type: KnowledgeType = KnowledgeType.RISK_ADVICE
    risk_type: list[str] = Field(default_factory=list)
    task_type: list[str] = Field(default_factory=list)
    warning_type: list[str] = Field(default_factory=list)
    warning_level: list[str] = Field(default_factory=list)
    decision_scope: list[str] = Field(default_factory=list)
    region: str | None = None
    province: str | None = None
    city: str | None = None
    visibility: KnowledgeVisibility = KnowledgeVisibility.PUBLIC
    tenant_id: str = "public"
    user_id: str | None = None
    version: str = "v1"
    effective_at: str | None = None
    expires_at: str | None = None
    review_status: KnowledgeReviewStatus = KnowledgeReviewStatus.APPROVED
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


class KnowledgeAccessContext(BaseModel):
    user_id: str | None = None
    tenant_id: str | None = None
    role: str | None = None


class KnowledgeBusinessContext(BaseModel):
    task_type: str | None = None
    risk_tags: list[str] = Field(default_factory=list)
    region: str | None = None
    province: str | None = None
    city: str | None = None


class KnowledgeRetrievalRequest(BaseModel):
    task_type: str
    overall_decision: str | None = None
    risk_reasons: list[str] = Field(default_factory=list)
    warning_types: list[str] = Field(default_factory=list)
    warning_levels: list[str] = Field(default_factory=list)
    region: str | None = None
    province: str | None = None
    city: str | None = None
    top_k: int = 5


class KnowledgeRetrievalResponse(BaseModel):
    context: AdviceRetrievalContext
    snippets: list[RetrievedKnowledgeSnippet] = Field(default_factory=list)
    advice: list[AdviceSuggestion] = Field(default_factory=list)
    retrieval_status: str = "success"
    retrieval_message: str | None = None
    retrieval_metadata: dict[str, object] = Field(default_factory=dict)
