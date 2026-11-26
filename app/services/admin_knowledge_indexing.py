import json
from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.db.models import KnowledgeDocument, KnowledgeIndexJob
from app.schemas import KnowledgeIndexJobListResponse, KnowledgeIndexJobResponse, KnowledgeIndexJobStatus
from app.schemas.advice import AdviceCategory, AdvicePriority, KnowledgeAdviceItem, KnowledgeAdviceLibrary
from app.services.knowledge_chunker import build_indexed_chunks
from app.services.vector_knowledge_store import DEFAULT_DB_KNOWLEDGE_PATH
from app.services.knowledge_index_versions import (
    build_bundle, index_lock, prepare_snapshot, publish_snapshot,
)
from app.services.knowledge_runtime_control import read_control, release_published_restrictions


def reindex_knowledge_documents(*, db: Session, triggered_by_user_id: str | None = None) -> KnowledgeIndexJobResponse:
    root = DEFAULT_DB_KNOWLEDGE_PATH.parent
    with index_lock(root):
        return _reindex_locked(db=db, root=root, triggered_by_user_id=triggered_by_user_id)


def _reindex_locked(*, db: Session, root, triggered_by_user_id) -> KnowledgeIndexJobResponse:
    job = KnowledgeIndexJob(
        status=KnowledgeIndexJobStatus.RUNNING.value,
        index_type="hybrid",
        triggered_by_user_id=triggered_by_user_id,
        started_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    indexed_ids = []
    metadata_committed = False
    try:
        captured_control = read_control(root)
        timestamps = {}
        library = build_approved_active_library(db=db, revisions=timestamps)
        chunk_count = len(build_indexed_chunks(library))
        snapshot = prepare_snapshot(root, library=library, origin="admin")
        snapshot.manifest["index_job_id"] = job.id
        _build_retrieval_indexes(snapshot)

        indexed_ids = [item.id for item in library.items]
        for document_id in indexed_ids:
            # An edit made during construction must remain pending publication.
            db.execute(update(KnowledgeDocument).where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.updated_at == timestamps[document_id],
            ).values(index_dirty=False), execution_options={"synchronize_session": False})

        job.status = KnowledgeIndexJobStatus.SUCCESS.value
        job.document_count = len(library.items)
        job.chunk_count = chunk_count
        job.finished_at = datetime.utcnow()
        job.error_message = None
        db.commit()
        metadata_committed = True
        publish_snapshot(snapshot)
    except Exception as exc:
        db.rollback()
        if metadata_committed and indexed_ids:
            db.execute(update(KnowledgeDocument).where(KnowledgeDocument.id.in_(indexed_ids)).values(index_dirty=True))
        job.status = KnowledgeIndexJobStatus.FAILED.value
        job.error_message = str(exc)
        job.finished_at = datetime.utcnow()
        db.commit()
        db.refresh(job)
    else:
        try:
            release_published_restrictions(captured=captured_control, published_items=library.items, version=snapshot.version, root=root)
        except Exception:
            # Publication is valid; leave restrictions in place on any control
            # failure. Never reopen a withdrawn item by falling back to disk.
            job.error_message = "新版已发布，但部分访问限制未解除，请重新发布。"
            db.commit()
            db.refresh(job)
        _clear_knowledge_runtime_caches()
        db.refresh(job)

    return to_index_job_response(job)


def list_knowledge_index_jobs(
    *,
    db: Session,
    page: int = 1,
    page_size: int = 20,
) -> KnowledgeIndexJobListResponse:
    safe_page = max(page, 1)
    safe_page_size = min(max(page_size, 1), 100)
    total = db.scalar(select(func.count()).select_from(KnowledgeIndexJob)) or 0
    jobs = db.scalars(
        select(KnowledgeIndexJob)
        .order_by(KnowledgeIndexJob.created_at.desc(), KnowledgeIndexJob.id.desc())
        .offset((safe_page - 1) * safe_page_size)
        .limit(safe_page_size)
    ).all()

    return KnowledgeIndexJobListResponse(
        items=[to_index_job_response(job) for job in jobs],
        page=safe_page,
        page_size=safe_page_size,
        total=total,
    )


def build_approved_active_library(*, db: Session, now: datetime | None = None, revisions: dict | None = None) -> KnowledgeAdviceLibrary:
    current_time = now or datetime.utcnow()
    documents = db.scalars(
        select(KnowledgeDocument)
        .where(
            KnowledgeDocument.review_status == "approved",
            KnowledgeDocument.is_active.is_(True),
            or_(KnowledgeDocument.effective_at.is_(None), KnowledgeDocument.effective_at <= current_time),
            or_(KnowledgeDocument.expires_at.is_(None), KnowledgeDocument.expires_at >= current_time),
        )
        .order_by(KnowledgeDocument.updated_at.desc(), KnowledgeDocument.id.desc())
    ).all()
    if revisions is not None:
        revisions.update({document.id: document.updated_at for document in documents})
    return KnowledgeAdviceLibrary(
        version=f"db-{current_time.strftime('%Y%m%d%H%M%S')}",
        items=[_document_to_advice_item(document) for document in documents],
    )


def to_index_job_response(job: KnowledgeIndexJob) -> KnowledgeIndexJobResponse:
    return KnowledgeIndexJobResponse(
        id=job.id,
        status=job.status,
        index_type=job.index_type,
        triggered_by_user_id=job.triggered_by_user_id,
        document_count=job.document_count,
        chunk_count=job.chunk_count,
        error_message=job.error_message,
        started_at=_datetime_to_iso(job.started_at),
        finished_at=_datetime_to_iso(job.finished_at),
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
    )


def _build_retrieval_indexes(snapshot) -> None:
    build_bundle(snapshot)


def _clear_knowledge_runtime_caches() -> None:
    from app.services.advice_retriever import load_advice_library

    load_advice_library.cache_clear()


def _document_to_advice_item(document: KnowledgeDocument) -> KnowledgeAdviceItem:
    return KnowledgeAdviceItem(
        id=document.id,
        category=_safe_category(document.category),
        knowledge_type=document.knowledge_type,
        risk_type=list(document.risk_tags_json or []),
        task_type=list(document.task_types_json or []),
        warning_type=list(document.warning_types_json or []),
        warning_level=list(document.warning_levels_json or []),
        decision_scope=list(document.decision_scopes_json or []),
        region=document.region,
        province=document.province,
        city=document.city,
        visibility=document.visibility,
        tenant_id=document.tenant_id,
        user_id=document.user_id,
        version=document.version,
        effective_at=_date_to_iso(document.effective_at),
        expires_at=_date_to_iso(document.expires_at),
        review_status=document.review_status,
        title=document.title,
        advice_text=document.content,
        priority=AdvicePriority.MEDIUM,
        keywords=list(document.keywords_json or []),
        source=document.source,
        source_url=document.source_url,
        notes=_metadata_notes(document.metadata_json),
    )


def _safe_category(value: str | None) -> AdviceCategory:
    if value:
        try:
            return AdviceCategory(value)
        except ValueError:
            pass
    return AdviceCategory.RISK_ADVICE


def _metadata_notes(metadata: dict | None) -> str | None:
    if not metadata:
        return None
    return json.dumps(metadata, ensure_ascii=False, sort_keys=True)


def _datetime_to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _date_to_iso(value: datetime | None) -> str | None:
    return value.date().isoformat() if value else None
