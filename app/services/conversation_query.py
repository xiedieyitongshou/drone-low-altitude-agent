from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import ConversationRecord
from app.schemas import ConversationDetailResponse, ConversationListResponse, ConversationSummary


def list_user_conversations(
    *,
    db: Session,
    user_id: str,
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    session_id: str | None = None,
    intent: str | None = None,
    parser_source: str | None = None,
) -> ConversationListResponse:
    safe_page = max(page, 1)
    safe_page_size = min(max(page_size, 1), 100)

    statement = select(ConversationRecord).where(ConversationRecord.user_id == user_id)
    statement = _apply_filters(
        statement,
        keyword=keyword,
        session_id=session_id,
        intent=intent,
        parser_source=parser_source,
    )

    total = len(db.scalars(statement).all())
    records = db.scalars(
        statement.order_by(ConversationRecord.created_at.desc())
        .offset((safe_page - 1) * safe_page_size)
        .limit(safe_page_size)
    ).all()

    return ConversationListResponse(
        items=[_to_summary(record) for record in records],
        page=safe_page,
        page_size=safe_page_size,
        total=total,
    )


def get_user_conversation_detail(
    *,
    db: Session,
    user_id: str,
    conversation_id: str,
) -> ConversationDetailResponse | None:
    record = db.scalar(
        select(ConversationRecord).where(
            ConversationRecord.user_id == user_id,
            ConversationRecord.conversation_id == conversation_id,
        )
    )
    if record is None:
        return None

    summary = _to_summary(record)
    return ConversationDetailResponse(
        **summary.model_dump(),
        parsed=record.parsed_json,
        context_used=record.context_used,
        explanation=record.explanation,
        response=record.response_json,
    )


def _apply_filters(
    statement,
    *,
    keyword: str | None,
    session_id: str | None,
    intent: str | None,
    parser_source: str | None,
):
    if session_id:
        statement = statement.where(ConversationRecord.session_id == session_id)
    if intent:
        statement = statement.where(ConversationRecord.intent == intent)
    if parser_source:
        statement = statement.where(ConversationRecord.parser_source == parser_source)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        if pattern != "%%":
            statement = statement.where(
                or_(
                    ConversationRecord.query.like(pattern),
                    ConversationRecord.message.like(pattern),
                    ConversationRecord.explanation.like(pattern),
                )
            )
    return statement


def _to_summary(record: ConversationRecord) -> ConversationSummary:
    return ConversationSummary(
        conversation_id=record.conversation_id,
        session_id=record.session_id,
        query=record.query,
        intent=record.intent,
        target_endpoint=record.target_endpoint,
        parser_source=record.parser_source,
        success=record.success,
        message=record.message,
        created_at=record.created_at.isoformat(),
    )
