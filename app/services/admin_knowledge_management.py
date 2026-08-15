from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import KnowledgeDocument
from app.schemas import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentListResponse,
    KnowledgeDocumentResponse,
    KnowledgeDocumentStatusUpdate,
    KnowledgeDocumentUpdate,
)


class KnowledgeManagementError(Exception):
    pass


class KnowledgeDocumentNotFoundError(KnowledgeManagementError):
    pass


def list_knowledge_documents(
    *,
    db: Session,
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    knowledge_type: str | None = None,
    review_status: str | None = None,
    is_active: bool | None = None,
    visibility: str | None = None,
    tenant_id: str | None = None,
    city: str | None = None,
    index_dirty: bool | None = None,
) -> KnowledgeDocumentListResponse:
    safe_page = max(page, 1)
    safe_page_size = min(max(page_size, 1), 100)
    filters = []

    if keyword:
        like_keyword = f"%{keyword.strip()}%"
        filters.append(or_(KnowledgeDocument.title.ilike(like_keyword), KnowledgeDocument.content.ilike(like_keyword)))
    if knowledge_type:
        filters.append(KnowledgeDocument.knowledge_type == knowledge_type)
    if review_status:
        filters.append(KnowledgeDocument.review_status == review_status)
    if is_active is not None:
        filters.append(KnowledgeDocument.is_active == is_active)
    if visibility:
        filters.append(KnowledgeDocument.visibility == visibility)
    if tenant_id:
        filters.append(KnowledgeDocument.tenant_id == tenant_id)
    if city:
        filters.append(KnowledgeDocument.city == city)
    if index_dirty is not None:
        filters.append(KnowledgeDocument.index_dirty == index_dirty)

    total_statement = select(func.count()).select_from(KnowledgeDocument)
    list_statement = select(KnowledgeDocument).order_by(KnowledgeDocument.updated_at.desc(), KnowledgeDocument.id.desc())
    if filters:
        total_statement = total_statement.where(*filters)
        list_statement = list_statement.where(*filters)

    total = db.scalar(total_statement) or 0
    documents = db.scalars(
        list_statement.offset((safe_page - 1) * safe_page_size).limit(safe_page_size)
    ).all()

    return KnowledgeDocumentListResponse(
        items=[to_knowledge_document_response(document) for document in documents],
        page=safe_page,
        page_size=safe_page_size,
        total=total,
    )


def create_knowledge_document(*, db: Session, payload: KnowledgeDocumentCreate) -> KnowledgeDocumentResponse:
    document = KnowledgeDocument(**_create_values(payload))
    db.add(document)
    db.commit()
    db.refresh(document)
    return to_knowledge_document_response(document)


def get_knowledge_document(*, db: Session, knowledge_id: str) -> KnowledgeDocumentResponse:
    return to_knowledge_document_response(_get_document(db=db, knowledge_id=knowledge_id))


def update_knowledge_document(
    *,
    db: Session,
    knowledge_id: str,
    payload: KnowledgeDocumentUpdate,
) -> KnowledgeDocumentResponse:
    document = _get_document(db=db, knowledge_id=knowledge_id)
    for field_name, value in _update_values(payload).items():
        setattr(document, field_name, value)
    document.index_dirty = True
    db.commit()
    db.refresh(document)
    return to_knowledge_document_response(document)


def soft_delete_knowledge_document(*, db: Session, knowledge_id: str) -> KnowledgeDocumentResponse:
    document = _get_document(db=db, knowledge_id=knowledge_id)
    document.is_active = False
    document.index_dirty = True
    db.commit()
    db.refresh(document)
    return to_knowledge_document_response(document)


def update_knowledge_document_status(
    *,
    db: Session,
    knowledge_id: str,
    payload: KnowledgeDocumentStatusUpdate,
) -> KnowledgeDocumentResponse:
    document = _get_document(db=db, knowledge_id=knowledge_id)
    if payload.review_status is not None:
        document.review_status = payload.review_status.value
    if payload.is_active is not None:
        document.is_active = payload.is_active
    if payload.index_dirty:
        document.index_dirty = True
    db.commit()
    db.refresh(document)
    return to_knowledge_document_response(document)


def to_knowledge_document_response(document: KnowledgeDocument) -> KnowledgeDocumentResponse:
    return KnowledgeDocumentResponse(
        id=document.id,
        title=document.title,
        content=document.content,
        knowledge_type=document.knowledge_type,
        category=document.category,
        region=document.region,
        province=document.province,
        city=document.city,
        task_types=list(document.task_types_json or []),
        risk_tags=list(document.risk_tags_json or []),
        warning_types=list(document.warning_types_json or []),
        warning_levels=list(document.warning_levels_json or []),
        decision_scopes=list(document.decision_scopes_json or []),
        keywords=list(document.keywords_json or []),
        visibility=document.visibility,
        tenant_id=document.tenant_id,
        user_id=document.user_id,
        version=document.version,
        review_status=document.review_status,
        is_active=document.is_active,
        index_dirty=document.index_dirty,
        effective_at=_datetime_to_iso(document.effective_at),
        expires_at=_datetime_to_iso(document.expires_at),
        source=document.source,
        source_url=document.source_url,
        metadata=dict(document.metadata_json or {}),
        created_at=document.created_at.isoformat(),
        updated_at=document.updated_at.isoformat(),
    )


def _get_document(*, db: Session, knowledge_id: str) -> KnowledgeDocument:
    document = db.get(KnowledgeDocument, knowledge_id)
    if document is None:
        raise KnowledgeDocumentNotFoundError("knowledge document not found")
    return document


def _create_values(payload: KnowledgeDocumentCreate) -> dict:
    return {
        "title": payload.title,
        "content": payload.content,
        "knowledge_type": payload.knowledge_type.value,
        "category": payload.category.value if payload.category else None,
        "region": payload.region,
        "province": payload.province,
        "city": payload.city,
        "task_types_json": list(payload.task_types),
        "risk_tags_json": list(payload.risk_tags),
        "warning_types_json": list(payload.warning_types),
        "warning_levels_json": list(payload.warning_levels),
        "decision_scopes_json": list(payload.decision_scopes),
        "keywords_json": list(payload.keywords),
        "visibility": payload.visibility.value,
        "tenant_id": payload.tenant_id,
        "user_id": payload.user_id,
        "version": payload.version,
        "review_status": payload.review_status.value,
        "is_active": payload.is_active,
        "index_dirty": True,
        "effective_at": _parse_datetime(payload.effective_at),
        "expires_at": _parse_datetime(payload.expires_at),
        "source": payload.source,
        "source_url": payload.source_url,
        "metadata_json": dict(payload.metadata),
    }


def _update_values(payload: KnowledgeDocumentUpdate) -> dict:
    raw_values = payload.model_dump(exclude_unset=True)
    values: dict = {}
    direct_fields = {
        "title",
        "content",
        "region",
        "province",
        "city",
        "tenant_id",
        "user_id",
        "version",
        "is_active",
        "source",
        "source_url",
    }
    for field_name in direct_fields:
        if field_name in raw_values:
            values[field_name] = raw_values[field_name]

    enum_fields = {"knowledge_type", "category", "visibility", "review_status"}
    for field_name in enum_fields:
        if field_name in raw_values:
            value = raw_values[field_name]
            values[field_name] = value.value if hasattr(value, "value") else value

    list_fields = {
        "task_types": "task_types_json",
        "risk_tags": "risk_tags_json",
        "warning_types": "warning_types_json",
        "warning_levels": "warning_levels_json",
        "decision_scopes": "decision_scopes_json",
        "keywords": "keywords_json",
    }
    for schema_field, model_field in list_fields.items():
        if schema_field in raw_values:
            values[model_field] = list(raw_values[schema_field] or [])

    if "effective_at" in raw_values:
        values["effective_at"] = _parse_datetime(raw_values["effective_at"])
    if "expires_at" in raw_values:
        values["expires_at"] = _parse_datetime(raw_values["expires_at"])
    if "metadata" in raw_values:
        values["metadata_json"] = dict(raw_values["metadata"] or {})
    return values


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None or not str(value).strip():
        return None
    return datetime.fromisoformat(str(value).strip())


def _datetime_to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
