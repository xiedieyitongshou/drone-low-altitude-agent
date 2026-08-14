from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RuleSetStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class RuleSetVisibility(StrEnum):
    PRIVATE = "private"
    TENANT = "tenant"
    PUBLIC = "public"
    SYSTEM = "system"


class RuleSetSource(StrEnum):
    USER = "user"
    SYSTEM = "system"


class RuleOperator(StrEnum):
    GREATER_THAN_OR_EQUAL = ">="
    EQUAL = "=="
    IN = "in"


class RuleDecision(StrEnum):
    SUITABLE = "适飞"
    CAUTION = "慎飞"
    PROHIBITED = "禁飞"


class RuleItemBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    metric: str
    operator: RuleOperator
    threshold_value: float | None = None
    threshold_text: str | None = None
    threshold_values: list[str | float | int] = Field(default_factory=list)
    unit: str | None = None
    decision: RuleDecision
    label: str
    risk_tag: str | None = None
    priority: int = 100
    enabled: bool = True


class RuleItemCreate(RuleItemBase):
    pass


class RuleItemUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    metric: str | None = None
    operator: RuleOperator | None = None
    threshold_value: float | None = None
    threshold_text: str | None = None
    threshold_values: list[str | float | int] | None = None
    unit: str | None = None
    decision: RuleDecision | None = None
    label: str | None = None
    risk_tag: str | None = None
    priority: int | None = None
    enabled: bool | None = None


class RuleItemResponse(RuleItemBase):
    id: str
    rule_set_id: str
    created_at: str
    updated_at: str


class RuleSetBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    description: str | None = None
    task_type: str = "cruise"
    visibility: RuleSetVisibility = RuleSetVisibility.PRIVATE
    tenant_id: str = "public"


class RuleSetCreate(RuleSetBase):
    items: list[RuleItemCreate] = Field(default_factory=list)


class RuleSetUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = None
    description: str | None = None
    task_type: str | None = None
    visibility: RuleSetVisibility | None = None
    tenant_id: str | None = None
    items: list[RuleItemCreate] | None = None


class RuleSetResponse(RuleSetBase):
    id: str
    owner_user_id: str | None = None
    version: int
    status: RuleSetStatus
    is_default: bool
    source: RuleSetSource
    validation_errors: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str
    items: list[RuleItemResponse] = Field(default_factory=list)


class RuleSetListResponse(BaseModel):
    items: list[RuleSetResponse] = Field(default_factory=list)
    page: int = 1
    page_size: int = 20
    total: int = 0
