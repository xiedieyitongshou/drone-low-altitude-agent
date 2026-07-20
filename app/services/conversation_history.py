from uuid import uuid4

from app.db.models import ConversationRecord
from app.db.session import SessionLocal
from app.schemas import OrchestratorResponse
from app.services.profile_memory import normalize_user_id


def persist_conversation_record(
    *,
    query: str,
    response: OrchestratorResponse,
    user_id: str | None = None,
) -> str:
    conversation_id = uuid4().hex
    with SessionLocal() as session:
        session.add(
            ConversationRecord(
                conversation_id=conversation_id,
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
        )
        session.commit()
    return conversation_id
