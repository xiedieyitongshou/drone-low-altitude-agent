from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.advice import AdviceCategory, KnowledgeReviewStatus, KnowledgeType, KnowledgeVisibility


class KnowledgeIndexJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class KnowledgeDocumentBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str
    content: str
    knowledge_type: KnowledgeType
    category: AdviceCategory | None = None
    region: str | None = None
    province: str | None = None
    city: str | None = None
    task_types: list[str] = Field(default_factory=list)
    risk_tags: list[str] = Field(default_factory=list)
    warning_types: list[str] = Field(default_factory=list)
    warning_levels: list[str] = Field(default_factory=list)
    decision_scopes: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    visibility: KnowledgeVisibility = KnowledgeVisibility.PUBLIC
    tenant_id: str = "public"
    user_id: str | None = None
    version: str = "v1"
    review_status: KnowledgeReviewStatus = KnowledgeReviewStatus.DRAFT
    is_active: bool = True
    index_dirty: bool = True
    effective_at: str | None = None
    expires_at: str | None = None
    source: str | None = None
    source_url: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class KnowledgeDocumentCreate(KnowledgeDocumentBase):
    pass


class KnowledgeDocumentUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = None
    content: str | None = None
    knowledge_type: KnowledgeType | None = None
    category: AdviceCategory | None = None
    region: str | None = None
    province: str | None = None
    city: str | None = None
    task_types: list[str] | None = None
    risk_tags: list[str] | None = None
    warning_types: list[str] | None = None
    warning_levels: list[str] | None = None
    decision_scopes: list[str] | None = None
    keywords: list[str] | None = None
    visibility: KnowledgeVisibility | None = None
    tenant_id: str | None = None
    user_id: str | None = None
    version: str | None = None
    review_status: KnowledgeReviewStatus | None = None
    is_active: bool | None = None
    index_dirty: bool | None = None
    effective_at: str | None = None
    expires_at: str | None = None
    source: str | None = None
    source_url: str | None = None
    metadata: dict[str, object] | None = None


class KnowledgeDocumentStatusUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    review_status: KnowledgeReviewStatus | None = None
    is_active: bool | None = None
    index_dirty: bool = True


class KnowledgeDocumentResponse(KnowledgeDocumentBase):
    id: str
    created_at: str
    updated_at: str


class KnowledgeDocumentListResponse(BaseModel):
    items: list[KnowledgeDocumentResponse] = Field(default_factory=list)
    page: int = 1
    page_size: int = 20
    total: int = 0


class KnowledgeIndexJobResponse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str
    status: KnowledgeIndexJobStatus
    index_type: str = "hybrid"
    triggered_by_user_id: str | None = None
    document_count: int = 0
    chunk_count: int = 0
    error_message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    created_at: str
    updated_at: str


class KnowledgeIndexJobListResponse(BaseModel):
    items: list[KnowledgeIndexJobResponse] = Field(default_factory=list)
    page: int = 1
    page_size: int = 20
    total: int = 0
