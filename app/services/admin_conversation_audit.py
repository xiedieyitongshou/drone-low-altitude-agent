from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import ConversationRecord, User
from app.schemas.admin import (
    AdminConversationDetailResponse,
    AdminConversationListResponse,
    AdminConversationSummary,
)


def list_admin_conversations(
    *,
    db: Session,
    page: int = 1,
    page_size: int = 20,
    user_id: str | None = None,
    session_id: str | None = None,
    intent: str | None = None,
    parser_source: str | None = None,
    success: bool | None = None,
    keyword: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> AdminConversationListResponse:
    safe_page = max(page, 1)
    safe_page_size = min(max(page_size, 1), 100)
    filters = _build_filters(
        user_id=user_id,
        session_id=session_id,
        intent=intent,
        parser_source=parser_source,
        success=success,
        keyword=keyword,
        created_from=created_from,
        created_to=created_to,
    )

    base_statement = select(ConversationRecord, User).join(User, ConversationRecord.user_id == User.id)
    count_statement = select(func.count()).select_from(ConversationRecord).join(
        User, ConversationRecord.user_id == User.id
    )
    if filters:
        base_statement = base_statement.where(*filters)
        count_statement = count_statement.where(*filters)

    total = db.scalar(count_statement) or 0
    rows = db.execute(
        base_statement.order_by(ConversationRecord.created_at.desc(), ConversationRecord.id.desc())
        .offset((safe_page - 1) * safe_page_size)
        .limit(safe_page_size)
    ).all()

    return AdminConversationListResponse(
        items=[_to_summary(record=record, user=user) for record, user in rows],
        page=safe_page,
        page_size=safe_page_size,
        total=total,
    )


def get_admin_conversation_detail(
    *,
    db: Session,
    conversation_id: str,
) -> AdminConversationDetailResponse | None:
    row = db.execute(
        select(ConversationRecord, User)
        .join(User, ConversationRecord.user_id == User.id)
        .where(ConversationRecord.conversation_id == conversation_id)
    ).one_or_none()
    if row is None:
        return None

    record, user = row
    summary = _to_summary(record=record, user=user)
    return AdminConversationDetailResponse(
        **summary.model_dump(),
        parsed=record.parsed_json,
        context_used=record.context_used,
        explanation=record.explanation,
        response=record.response_json,
    )


def _build_filters(
    *,
    user_id: str | None,
    session_id: str | None,
    intent: str | None,
    parser_source: str | None,
    success: bool | None,
    keyword: str | None,
    created_from: datetime | None,
    created_to: datetime | None,
):
    filters = []
    if user_id:
        filters.append(ConversationRecord.user_id == user_id)
    if session_id:
        filters.append(ConversationRecord.session_id == session_id)
    if intent:
        filters.append(ConversationRecord.intent == intent)
    if parser_source:
        filters.append(ConversationRecord.parser_source == parser_source)
    if success is not None:
        filters.append(ConversationRecord.success == success)
    if created_from is not None:
        filters.append(ConversationRecord.created_at >= created_from)
    if created_to is not None:
        filters.append(ConversationRecord.created_at <= created_to)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        if pattern != "%%":
            filters.append(
                or_(
                    ConversationRecord.query.like(pattern),
                    ConversationRecord.message.like(pattern),
                    ConversationRecord.explanation.like(pattern),
                    User.username.like(pattern),
                    User.display_name.like(pattern),
                )
            )
    return filters


def _to_summary(*, record: ConversationRecord, user: User) -> AdminConversationSummary:
    return AdminConversationSummary(
        conversation_id=record.conversation_id,
        session_id=record.session_id,
        user_id=record.user_id,
        username=user.username,
        display_name=user.display_name,
        query=record.query,
        intent=record.intent,
        target_endpoint=record.target_endpoint,
        parser_source=record.parser_source,
        success=record.success,
        message=record.message,
        created_at=record.created_at.isoformat(),
    )
