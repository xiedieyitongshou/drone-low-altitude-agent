from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ConversationRecord, User
from app.schemas.admin import AdminTaskStatsResponse


HIGH_RISK_DECISIONS = {"禁飞", "不适飞", "禁止飞行", "高风险"}


def get_admin_task_stats(*, db: Session) -> AdminTaskStatsResponse:
    total_users = db.scalar(select(func.count()).select_from(User)) or 0
    active_users = db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))) or 0
    disabled_users = db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(False))) or 0
    admin_users = db.scalar(select(func.count()).select_from(User).where(User.role == "admin")) or 0
    total_tasks = db.scalar(select(func.count()).select_from(ConversationRecord)) or 0
    successful_tasks = (
        db.scalar(select(func.count()).select_from(ConversationRecord).where(ConversationRecord.success.is_(True)))
        or 0
    )
    failed_tasks = (
        db.scalar(select(func.count()).select_from(ConversationRecord).where(ConversationRecord.success.is_(False)))
        or 0
    )

    records = db.scalars(select(ConversationRecord)).all()
    high_risk_tasks = sum(1 for record in records if _is_high_risk(record))
    rule_rejected_tasks = sum(1 for record in records if _is_rule_rejected(record))
    parser_failed_tasks = sum(1 for record in records if _is_parser_failed(record))

    return AdminTaskStatsResponse(
        total_users=total_users,
        active_users=active_users,
        disabled_users=disabled_users,
        admin_users=admin_users,
        total_tasks=total_tasks,
        successful_tasks=successful_tasks,
        failed_tasks=failed_tasks,
        high_risk_tasks=high_risk_tasks,
        rule_rejected_tasks=rule_rejected_tasks,
        parser_failed_tasks=parser_failed_tasks,
    )


def _is_high_risk(record: ConversationRecord) -> bool:
    values = _collect_decision_values(record.response_json)
    values.extend(_collect_decision_values(record.parsed_json))
    values.extend([record.message or "", record.explanation or ""])
    return any(any(decision in value for decision in HIGH_RISK_DECISIONS) for value in values)


def _is_rule_rejected(record: ConversationRecord) -> bool:
    response = record.response_json or {}
    values = _collect_decision_values(response)
    if any("禁飞" in value or "不适飞" in value for value in values):
        return True

    if response.get("allow_execute") is False or response.get("allow_cruise") is False:
        return True

    advice = response.get("advice")
    if isinstance(advice, dict) and advice.get("allow_cruise") is False:
        return True

    return False


def _is_parser_failed(record: ConversationRecord) -> bool:
    if record.success:
        return False

    text = " ".join(
        value
        for value in [
            record.message or "",
            record.explanation or "",
            record.parser_source or "",
        ]
        if value
    ).lower()
    return any(keyword in text for keyword in ["parse", "parser", "解析"])


def _collect_decision_values(payload: dict | None) -> list[str]:
    if not isinstance(payload, dict):
        return []

    values: list[str] = []
    for key in ["overall_decision", "decision", "risk_level", "status"]:
        value = payload.get(key)
        if isinstance(value, str):
            values.append(value)

    advice = payload.get("advice")
    if isinstance(advice, dict):
        values.extend(_collect_decision_values(advice))

    return values
