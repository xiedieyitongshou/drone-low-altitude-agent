from uuid import uuid4
from sqlalchemy.orm import Session

from app.db.models import ConversationRecord
from app.db.session import SessionLocal
from app.schemas import OrchestratorResponse
from app.services.profile_memory import normalize_user_id


def persist_conversation_record(
    *,
    query: str,
    response: OrchestratorResponse,
    user_id: str | None = None,
    db: Session | None = None,
) -> str:
    conversation_id = uuid4().hex
    response.conversation_id = conversation_id
    record = ConversationRecord(
        conversation_id=conversation_id,
        trace_id=response.trace_id,
        request_id=response.request_id,
        session_id=response.session_id,
        user_id=normalize_user_id(user_id),
        query=query,
        intent=response.intent,
        target_endpoint=response.target_endpoint,
        parser_source=response.parser_source,
        parsed_json=response.parsed,
        context_used=response.context_used,
        success=response.success,
        message=response.message,
        explanation=response.composed.explanation if response.composed else None,
        response_json=response.model_dump(mode="json"),
    )
    if db is not None:
        try:
            db.add(record)
            db.commit()
        except Exception:
            db.rollback()
            raise
        return conversation_id
    with SessionLocal() as session:
        session.add(record)
        session.commit()
    return conversation_id
