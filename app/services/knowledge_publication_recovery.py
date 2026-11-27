"""Reconcile publication metadata with the actual pointer under the build lock."""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import KnowledgeDocument, KnowledgeIndexJob
from app.db.session import SessionLocal
from app.schemas.advice import KnowledgeAdviceLibrary
from app.services.knowledge_index_versions import (
    KnowledgeIndexBusyError, KnowledgeSnapshot, current_snapshot, default_index_root,
    filesystem_path, index_lock, snapshot_for_version, validate_bundle,
)
from app.services.knowledge_runtime_control import release_published_restrictions


logger = logging.getLogger(__name__)
RECOVERY_INTERVAL_SECONDS = 60


def publication_context(snapshot: KnowledgeSnapshot, job: KnowledgeIndexJob):
    manifest = snapshot.manifest
    context = manifest.get("publication", {})
    if manifest.get("origin") != "admin" or manifest.get("index_job_id") != job.id:
        raise ValueError("Knowledge publication does not belong to the job")
    if not isinstance(context, dict) or context.get("schema_version") != 1 or not isinstance(context.get("captured_control"), dict):
        raise ValueError("Missing knowledge publication recovery context")
    if not isinstance(context["captured_control"].get("documents"), dict):
        raise ValueError("Missing knowledge publication recovery context")
    library = KnowledgeAdviceLibrary.model_validate_json(snapshot.source.read_text(encoding="utf-8-sig"))
    revisions = context.get("document_revisions")
    if not isinstance(revisions, dict) or set(revisions) != {item.id for item in library.items}:
        raise ValueError("Knowledge publication revisions do not match its source")
    return library, {key: datetime.fromisoformat(value) for key, value in revisions.items()}, context["captured_control"]


def finish_published_job(*, db: Session, job: KnowledgeIndexJob, snapshot: KnowledgeSnapshot) -> None:
    """Repeat safely after a crash, including one during restriction release."""
    library, revisions, captured = publication_context(snapshot, job)
    warning = None
    try:
        release_published_restrictions(captured=captured, published_items=library.items, version=snapshot.version, root=snapshot.root)
    except Exception:
        logger.exception("Knowledge publication restrictions remain in place for job %s", job.id)
        warning = "新版已发布，但部分访问限制未解除，请重新发布。"
    for document_id, revision in revisions.items():
        db.execute(update(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.updated_at == revision,
        ).values(index_dirty=False, updated_at=KnowledgeDocument.updated_at), execution_options={"synchronize_session": False})
    job.status = "success"
    job.publication_phase = "completed"
    job.document_count = len(library.items)
    job.finished_at = datetime.utcnow()
    job.error_message = warning
    db.commit()
    clear_knowledge_runtime_caches()


def clear_knowledge_runtime_caches() -> None:
    from app.services.advice_retriever import load_advice_library

    load_advice_library.cache_clear()


def fail_interrupted_job(*, db: Session, job: KnowledgeIndexJob, message: str) -> None:
    # New publishers never clear pending flags before switching the pointer.
    job.status = "failed"
    job.publication_phase = "failed"
    job.error_message = message
    job.finished_at = datetime.utcnow()
    db.commit()


def _repair_latest_legacy_success(*, db: Session, root: Path, active: KnowledgeSnapshot | None) -> int:
    """Repair only a provable pre-upgrade gap, never superseded successes."""
    latest = db.scalars(select(KnowledgeIndexJob).order_by(
        KnowledgeIndexJob.created_at.desc(), KnowledgeIndexJob.id.desc(),
    ).limit(1)).first()
    if latest is None or latest.publication_phase is not None or latest.status != "success":
        return 0
    active_job_id = active.manifest.get("index_job_id") if active else None
    if active_job_id == latest.id:
        latest.index_version = active.version
        latest.publication_phase = "completed"
        db.commit()
        return 1
    if active:
        active_job = db.get(KnowledgeIndexJob, active_job_id) if active_job_id else None
        if active_job is None or active_job.created_at >= latest.created_at:
            return 0
    candidates = []
    for path in filesystem_path(root / "versions").glob("admin-*/manifest.json"):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(manifest, dict) and manifest.get("index_job_id") == latest.id:
                candidates.append(snapshot_for_version(root, path.parent.name))
        except (OSError, ValueError):
            continue
    if len(candidates) != 1:
        return 0
    candidate = candidates[0]
    # Only source IDs are needed to restore conservative pending flags. A broken
    # candidate must never be activated, even if its old DB job says success.
    try:
        library = KnowledgeAdviceLibrary.model_validate_json(candidate.source.read_text(encoding="utf-8-sig"))
        pending = update(KnowledgeDocument).where(KnowledgeDocument.id.in_([item.id for item in library.items]))
    except (OSError, ValueError):
        # Pre-upgrade jobs have no durable revision list. If their source is lost,
        # conservatively retain every document as pending rather than claim that
        # an unknown subset has been published.
        pending = update(KnowledgeDocument)
    db.execute(pending.values(index_dirty=True, updated_at=KnowledgeDocument.updated_at), execution_options={"synchronize_session": False})
    latest.index_version = candidate.version
    fail_interrupted_job(db=db, job=latest, message="检测到升级前的发布中断：数据库曾记录成功，但索引未切换。已恢复待发布，请重新发布。")
    return 1


def recover_locked(*, db: Session, root: Path) -> int:
    """Caller owns the same cross-process lock used by publication."""
    pointer_error = None
    try:
        active = current_snapshot(root)
    except (OSError, ValueError, TypeError) as exc:
        active = None
        pointer_error = exc
        logger.error("Cannot validate the current knowledge publication: %s", exc)
    recovered = 0 if pointer_error else _repair_latest_legacy_success(db=db, root=root, active=active)
    jobs = db.scalars(select(KnowledgeIndexJob).where(
        KnowledgeIndexJob.status.in_(("pending", "running")),
    ).order_by(KnowledgeIndexJob.created_at, KnowledgeIndexJob.id)).all()
    for job in jobs:
        if pointer_error:
            fail_interrupted_job(db=db, job=job, message=f"发布恢复校验失败，未改变当前索引指针，请检查索引：{pointer_error}")
        elif active is not None and job.index_version == active.version:
            try:
                validate_bundle(active)
                publication_context(active, job)
            except Exception as exc:
                fail_interrupted_job(db=db, job=job, message=f"发布恢复校验失败，未改变当前索引指针，请检查索引：{exc}")
            else:
                # DB errors propagate so that the durable running job is retried.
                finish_published_job(db=db, job=job, snapshot=active)
        else:
            fail_interrupted_job(db=db, job=job, message="发布进程中断，索引未切换；当前版本继续使用，请重新发布。")
        recovered += 1
    return recovered


def recover_knowledge_publications(*, db: Session, root: Path | None = None) -> int:
    root = root or default_index_root()
    try:
        with index_lock(root):
            return recover_locked(db=db, root=root)
    except KnowledgeIndexBusyError:
        # A live builder owns the lock. Elapsed time alone is not a crash signal.
        return 0


def recover_pending_knowledge_publications() -> int:
    try:
        with SessionLocal() as db:
            return recover_knowledge_publications(db=db)
    except Exception:
        logger.exception("Knowledge publication recovery failed; will retry")
        return 0


async def run_knowledge_publication_recovery(*, interval_seconds: float = RECOVERY_INTERVAL_SECONDS) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        await asyncio.to_thread(recover_pending_knowledge_publications)
