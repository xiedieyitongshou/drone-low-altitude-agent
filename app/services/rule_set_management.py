from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import RuleItem, RuleSet, User
from app.rules import validate_rule_set
from app.schemas.rule_set import (
    RuleItemCreate,
    RuleItemResponse,
    RuleItemUpdate,
    RuleSetCreate,
    RuleSetListResponse,
    RuleSetResponse,
    RuleSetStatus,
    RuleSetUpdate,
    RuleSetVisibility,
)


class RuleSetNotFoundError(LookupError):
    pass


class RuleSetPermissionError(PermissionError):
    pass


class RuleSetActivationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("rule set validation failed")
        self.errors = errors


@dataclass(frozen=True)
class RuleSetAccess:
    current_user: User

    @property
    def is_admin(self) -> bool:
        return self.current_user.role == "admin"

    @property
    def user_id(self) -> str:
        return self.current_user.id


def list_rule_sets(
    *,
    db: Session,
    current_user: User,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    visibility: str | None = None,
    task_type: str | None = None,
) -> RuleSetListResponse:
    access = RuleSetAccess(current_user=current_user)
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    statement = _visible_rule_sets_statement(access)

    if status:
        statement = statement.where(RuleSet.status == status)
    if visibility:
        statement = statement.where(RuleSet.visibility == visibility)
    if task_type:
        statement = statement.where(RuleSet.task_type == task_type)

    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.scalars(
        statement.order_by(RuleSet.updated_at.desc(), RuleSet.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique().all()

    return RuleSetListResponse(
        items=[to_rule_set_response(rule_set) for rule_set in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


def create_rule_set(*, db: Session, current_user: User, payload: RuleSetCreate) -> RuleSetResponse:
    access = RuleSetAccess(current_user=current_user)
    _ensure_visibility_can_be_written(access, payload.visibility)

    rule_set = RuleSet(
        name=payload.name,
        description=payload.description,
        task_type=payload.task_type,
        owner_user_id=access.user_id,
        tenant_id=payload.tenant_id,
        visibility=payload.visibility.value,
        status=RuleSetStatus.DRAFT.value,
        version=1,
        source="user",
        items=[_build_rule_item(item) for item in payload.items],
    )
    db.add(rule_set)
    db.commit()
    db.refresh(rule_set)
    return to_rule_set_response(rule_set)


def get_rule_set(*, db: Session, current_user: User, rule_set_id: str) -> RuleSetResponse:
    rule_set = _get_accessible_rule_set(db=db, current_user=current_user, rule_set_id=rule_set_id)
    return to_rule_set_response(rule_set)


def update_rule_set(
    *,
    db: Session,
    current_user: User,
    rule_set_id: str,
    payload: RuleSetUpdate,
) -> RuleSetResponse:
    rule_set = _get_accessible_rule_set(db=db, current_user=current_user, rule_set_id=rule_set_id)
    access = RuleSetAccess(current_user=current_user)
    _ensure_can_modify(access, rule_set)

    if payload.visibility is not None:
        _ensure_visibility_can_be_written(access, payload.visibility)

    if payload.name is not None:
        rule_set.name = payload.name
    if payload.description is not None:
        rule_set.description = payload.description
    if payload.task_type is not None:
        rule_set.task_type = payload.task_type
    if payload.visibility is not None:
        rule_set.visibility = payload.visibility.value
    if payload.tenant_id is not None:
        rule_set.tenant_id = payload.tenant_id
    if payload.items is not None:
        rule_set.items = [_build_rule_item(item) for item in payload.items]

    rule_set.status = RuleSetStatus.DRAFT.value
    rule_set.validation_errors_json = []
    db.commit()
    db.refresh(rule_set)
    return to_rule_set_response(rule_set)


def add_rule_item(
    *,
    db: Session,
    current_user: User,
    rule_set_id: str,
    payload: RuleItemCreate,
) -> RuleSetResponse:
    rule_set = _get_accessible_rule_set(db=db, current_user=current_user, rule_set_id=rule_set_id)
    _ensure_can_modify(RuleSetAccess(current_user=current_user), rule_set)
    rule_set.items.append(_build_rule_item(payload))
    _mark_draft(rule_set)
    db.commit()
    db.refresh(rule_set)
    return to_rule_set_response(rule_set)


def update_rule_item(
    *,
    db: Session,
    current_user: User,
    rule_set_id: str,
    item_id: str,
    payload: RuleItemUpdate,
) -> RuleSetResponse:
    rule_set = _get_accessible_rule_set(db=db, current_user=current_user, rule_set_id=rule_set_id)
    _ensure_can_modify(RuleSetAccess(current_user=current_user), rule_set)
    item = _find_rule_item(rule_set, item_id)

    for field_name in (
        "metric",
        "operator",
        "threshold_value",
        "threshold_text",
        "threshold_values",
        "unit",
        "decision",
        "label",
        "risk_tag",
        "priority",
        "enabled",
    ):
        value = getattr(payload, field_name)
        if value is None:
            continue
        if field_name == "operator":
            item.operator = value.value
        elif field_name == "decision":
            item.decision = value.value
        elif field_name == "threshold_values":
            item.threshold_values_json = list(value)
        else:
            setattr(item, field_name, value)

    _mark_draft(rule_set)
    db.commit()
    db.refresh(rule_set)
    return to_rule_set_response(rule_set)


def delete_rule_item(
    *,
    db: Session,
    current_user: User,
    rule_set_id: str,
    item_id: str,
) -> RuleSetResponse:
    rule_set = _get_accessible_rule_set(db=db, current_user=current_user, rule_set_id=rule_set_id)
    _ensure_can_modify(RuleSetAccess(current_user=current_user), rule_set)
    item = _find_rule_item(rule_set, item_id)
    rule_set.items.remove(item)
    _mark_draft(rule_set)
    db.commit()
    db.refresh(rule_set)
    return to_rule_set_response(rule_set)


def validate_and_store_rule_set(*, db: Session, current_user: User, rule_set_id: str) -> RuleSetResponse:
    rule_set = _get_accessible_rule_set(db=db, current_user=current_user, rule_set_id=rule_set_id)
    _ensure_can_modify(RuleSetAccess(current_user=current_user), rule_set)
    validation = validate_rule_set(rule_set.items)
    rule_set.validation_errors_json = validation.messages
    db.commit()
    db.refresh(rule_set)
    return to_rule_set_response(rule_set)


def activate_rule_set(*, db: Session, current_user: User, rule_set_id: str) -> RuleSetResponse:
    rule_set = _get_accessible_rule_set(db=db, current_user=current_user, rule_set_id=rule_set_id)
    _ensure_can_modify(RuleSetAccess(current_user=current_user), rule_set)
    validation = validate_rule_set(rule_set.items)
    rule_set.validation_errors_json = validation.messages
    if not validation.is_valid:
        db.commit()
        raise RuleSetActivationError(validation.messages)

    rule_set.status = RuleSetStatus.ACTIVE.value
    db.commit()
    db.refresh(rule_set)
    return to_rule_set_response(rule_set)


def to_rule_set_response(rule_set: RuleSet) -> RuleSetResponse:
    return RuleSetResponse(
        id=rule_set.id,
        name=rule_set.name,
        description=rule_set.description,
        task_type=rule_set.task_type,
        visibility=RuleSetVisibility(rule_set.visibility),
        tenant_id=rule_set.tenant_id,
        owner_user_id=rule_set.owner_user_id,
        version=rule_set.version,
        status=RuleSetStatus(rule_set.status),
        is_default=rule_set.is_default,
        source=rule_set.source,
        validation_errors=list(rule_set.validation_errors_json or []),
        created_at=rule_set.created_at.isoformat(),
        updated_at=rule_set.updated_at.isoformat(),
        items=[to_rule_item_response(item) for item in rule_set.items],
    )


def to_rule_item_response(item: RuleItem) -> RuleItemResponse:
    return RuleItemResponse(
        id=item.id,
        rule_set_id=item.rule_set_id,
        metric=item.metric,
        operator=item.operator,
        threshold_value=item.threshold_value,
        threshold_text=item.threshold_text,
        threshold_values=list(item.threshold_values_json or []),
        unit=item.unit,
        decision=item.decision,
        label=item.label,
        risk_tag=item.risk_tag,
        priority=item.priority,
        enabled=item.enabled,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
    )


def _visible_rule_sets_statement(access: RuleSetAccess) -> Select[tuple[RuleSet]]:
    statement = select(RuleSet)
    if access.is_admin:
        return statement
    return statement.where(
        or_(
            RuleSet.owner_user_id == access.user_id,
            RuleSet.visibility.in_([RuleSetVisibility.PUBLIC.value, RuleSetVisibility.SYSTEM.value]),
        )
    )


def _get_accessible_rule_set(*, db: Session, current_user: User, rule_set_id: str) -> RuleSet:
    access = RuleSetAccess(current_user=current_user)
    rule_set = db.get(RuleSet, rule_set_id)
    if rule_set is None:
        raise RuleSetNotFoundError("rule set not found")
    if access.is_admin or rule_set.owner_user_id == access.user_id or rule_set.visibility in {
        RuleSetVisibility.PUBLIC.value,
        RuleSetVisibility.SYSTEM.value,
    }:
        return rule_set
    raise RuleSetNotFoundError("rule set not found")


def _ensure_can_modify(access: RuleSetAccess, rule_set: RuleSet) -> None:
    if access.is_admin:
        return
    if rule_set.owner_user_id == access.user_id and rule_set.visibility == RuleSetVisibility.PRIVATE.value:
        return
    raise RuleSetPermissionError("cannot modify this rule set")


def _ensure_visibility_can_be_written(access: RuleSetAccess, visibility: RuleSetVisibility) -> None:
    if visibility == RuleSetVisibility.PRIVATE:
        return
    if access.is_admin and visibility in {RuleSetVisibility.PUBLIC, RuleSetVisibility.TENANT}:
        return
    raise RuleSetPermissionError("only admin can maintain public or tenant rule sets")


def _build_rule_item(payload: RuleItemCreate) -> RuleItem:
    return RuleItem(
        metric=payload.metric,
        operator=payload.operator.value,
        threshold_value=payload.threshold_value,
        threshold_text=payload.threshold_text,
        threshold_values_json=list(payload.threshold_values),
        unit=payload.unit,
        decision=payload.decision.value,
        label=payload.label,
        risk_tag=payload.risk_tag,
        priority=payload.priority,
        enabled=payload.enabled,
    )


def _find_rule_item(rule_set: RuleSet, item_id: str) -> RuleItem:
    for item in rule_set.items:
        if item.id == item_id:
            return item
    raise RuleSetNotFoundError("rule item not found")


def _mark_draft(rule_set: RuleSet) -> None:
    rule_set.status = RuleSetStatus.DRAFT.value
    rule_set.validation_errors_json = []
