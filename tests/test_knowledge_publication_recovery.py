import asyncio
import subprocess
import sys
from contextlib import suppress
from threading import Event

import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import KnowledgeDocument, KnowledgeIndexJob
from app.schemas.knowledge import KnowledgeDocumentStatusUpdate, KnowledgeDocumentUpdate
from app.services import admin_knowledge_indexing as indexing
from app.services import knowledge_publication_recovery as recovery
from app.services.admin_knowledge_management import (
    soft_delete_knowledge_document, update_knowledge_document, update_knowledge_document_status,
)
from app.services.knowledge_index_versions import (
    atomic_json, current_snapshot, default_index_root, index_lock, snapshot_for_version,
)
from app.services.knowledge_retrievers import create_default_knowledge_retriever
from app.services.knowledge_runtime_control import read_control, set_retrieval_maintenance


# Keep the real entry point while the shared API fixture disables its live-DB
# invocation by default. Its module globals still accept an isolated factory.
runtime_recovery = recovery.recover_pending_knowledge_publications


@pytest.fixture
def publication_db(tmp_path, monkeypatch):
    monkeypatch.delenv("KNOWLEDGE_SOURCE_PATH", raising=False)
    monkeypatch.setenv("KNOWLEDGE_RETRIEVER", "hybrid")
    monkeypatch.setenv("LLM_ENABLED", "false")
    engine = create_engine(f"sqlite:///{(tmp_path / 'recovery.db').as_posix()}", connect_args={"check_same_thread": False})
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with factory() as db:
        db.add(KnowledgeDocument(id="old-policy", title="wind inspection", content="wind inspection original guidance", knowledge_type="risk_advice", review_status="approved", is_active=True))
        db.commit()
        assert indexing.reindex_knowledge_documents(db=db).status == "success"
        db.add(KnowledgeDocument(id="new-policy", title="wind inspection addition", content="wind inspection additional guidance", knowledge_type="risk_advice", review_status="approved", is_active=True))
        db.commit()
    yield factory
    engine.dispose()


CRASH_SCRIPT = r"""
import os, sys
from pathlib import Path
os.environ.update(DATABASE_URL=sys.argv[1], KNOWLEDGE_SOURCE_PATH="", KNOWLEDGE_RETRIEVER="hybrid", LLM_ENABLED="false")
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.services import admin_knowledge_indexing as indexing, knowledge_publication_recovery as recovery, vector_knowledge_store as vector
root, checkpoint = Path(sys.argv[2]), sys.argv[3]
vector.DEFAULT_INDEX_DIR = root
vector.DEFAULT_DB_KNOWLEDGE_PATH = root / "knowledge_documents_source.json"
indexing.DEFAULT_DB_KNOWLEDGE_PATH = vector.DEFAULT_DB_KNOWLEDGE_PATH
engine = create_engine(sys.argv[1])
factory = sessionmaker(bind=engine, expire_on_commit=False)
with factory() as db:
    original_commit = db.commit
    def commit():
        jobs = [item for item in db.identity_map.values() if isinstance(item, indexing.KnowledgeIndexJob)]
        if checkpoint == "before_final_commit" and any(item.status == "success" for item in jobs):
            os._exit(71)
        original_commit()
        if checkpoint in {"ready", "publishing"} and any(item.publication_phase == checkpoint for item in jobs):
            os._exit(71)
        if checkpoint == "after_final_commit" and any(item.status == "success" for item in jobs):
            os._exit(71)
    db.commit = commit
    original_build = indexing._build_retrieval_indexes
    def build(snapshot):
        if checkpoint == "during_build":
            os._exit(71)
        original_build(snapshot)
        if checkpoint == "after_build":
            os._exit(71)
    indexing._build_retrieval_indexes = build
    original_publish = indexing.publish_snapshot
    def publish(snapshot):
        if checkpoint == "before_pointer":
            os._exit(71)
        original_publish(snapshot)
        if checkpoint == "after_pointer":
            os._exit(71)
    indexing.publish_snapshot = publish
    original_release = recovery.release_published_restrictions
    def release(**kwargs):
        original_release(**kwargs)
        if checkpoint == "during_controls":
            os._exit(71)
    recovery.release_published_restrictions = release
    indexing.reindex_knowledge_documents(db=db)
raise AssertionError("crash checkpoint did not execute")
"""


def crash(factory, checkpoint):
    with factory() as db:
        url = str(db.get_bind().url)
    result = subprocess.run([sys.executable, "-c", CRASH_SCRIPT, url, str(default_index_root()), checkpoint], capture_output=True, text=True, timeout=30)
    assert result.returncode == 71, result.stdout + result.stderr


def latest(db):
    return db.scalars(select(KnowledgeIndexJob).order_by(KnowledgeIndexJob.created_at.desc(), KnowledgeIndexJob.id.desc()).limit(1)).one()


def recover(factory):
    with factory() as db:
        return recovery.recover_knowledge_publications(db=db)


def ids():
    return {item.id for item in create_default_knowledge_retriever().retrieve("wind inspection", top_k=10)}


@pytest.mark.parametrize("checkpoint,switched,completed", [
    ("during_build", False, False), ("after_build", False, False),
    ("ready", False, False), ("publishing", False, False),
    ("before_pointer", False, False), ("after_pointer", True, False),
    ("during_controls", True, False), ("before_final_commit", True, False),
    ("after_final_commit", True, True),
])
def test_abrupt_exit_recovers_from_actual_pointer(publication_db, checkpoint, switched, completed):
    old = current_snapshot(default_index_root()).version
    crash(publication_db, checkpoint)
    with publication_db() as db:
        job = latest(db)
        assert job.status == ("success" if completed else "running")
        assert db.get(KnowledgeDocument, "new-policy").index_dirty is not completed
        assert (current_snapshot(default_index_root()).version != old) is switched
        job_id = job.id
    assert recover(publication_db) == (0 if completed else 1)
    assert recover(publication_db) == 0
    with publication_db() as db:
        job = db.get(KnowledgeIndexJob, job_id)
        assert job.status == ("success" if switched else "failed")
        assert job.publication_phase == ("completed" if switched else "failed")
        assert db.get(KnowledgeDocument, "new-policy").index_dirty is not switched
    assert ids() == ({"old-policy", "new-policy"} if switched else {"old-policy"})


def test_recovery_skips_a_live_builder_and_retries_after_lock_release(publication_db):
    crash(publication_db, "after_pointer")
    with index_lock(default_index_root()):
        assert recover(publication_db) == 0
        with publication_db() as db:
            assert latest(db).status == "running"
    assert recover(publication_db) == 1


def test_recovery_preserves_later_edits_withdrawal_and_pause(publication_db):
    crash(publication_db, "after_pointer")
    with publication_db() as db:
        update_knowledge_document(db=db, knowledge_id="old-policy", payload=KnowledgeDocumentUpdate(content="wind inspection later edit"))
        soft_delete_knowledge_document(db=db, knowledge_id="new-policy")
    set_retrieval_maintenance(paused=True)
    assert recover(publication_db) == 1
    with publication_db() as db:
        assert latest(db).status == "success"
        assert db.get(KnowledgeDocument, "old-policy").index_dirty is True
        assert db.get(KnowledgeDocument, "new-policy").index_dirty is True
    assert read_control()["paused"] is True
    assert read_control()["documents"]["new-policy"]["blocked"] is True
    set_retrieval_maintenance(paused=False)
    assert ids() == {"old-policy"}
    assert all("original guidance" in item.content for item in create_default_knowledge_retriever().retrieve("wind inspection", top_k=10))


@pytest.mark.parametrize("checkpoint", ["after_pointer", "during_controls"])
def test_restriction_release_resumes_without_reopening_old_versions(publication_db, checkpoint):
    old_reader = create_default_knowledge_retriever()
    with publication_db() as db:
        soft_delete_knowledge_document(db=db, knowledge_id="old-policy")
        update_knowledge_document_status(db=db, knowledge_id="old-policy", payload=KnowledgeDocumentStatusUpdate(is_active=True))
    crash(publication_db, checkpoint)
    assert recover(publication_db) == 1
    assert recover(publication_db) == 0
    assert ids() == {"old-policy", "new-policy"}
    assert old_reader.retrieve("wind inspection", top_k=10) == []


def test_new_withdrawal_during_recovery_cannot_be_released(publication_db, monkeypatch):
    with publication_db() as db:
        soft_delete_knowledge_document(db=db, knowledge_id="old-policy")
        update_knowledge_document_status(db=db, knowledge_id="old-policy", payload=KnowledgeDocumentStatusUpdate(is_active=True))
    crash(publication_db, "after_pointer")
    release = recovery.release_published_restrictions
    def withdraw_then_release(**kwargs):
        with publication_db() as db:
            soft_delete_knowledge_document(db=db, knowledge_id="old-policy")
        release(**kwargs)
    monkeypatch.setattr(recovery, "release_published_restrictions", withdraw_then_release)
    assert recover(publication_db) == 1
    assert ids() == {"new-policy"}
    with publication_db() as db:
        assert db.get(KnowledgeDocument, "old-policy").index_dirty is True


def test_post_replace_exception_leaves_recoverable_job(publication_db, monkeypatch):
    publish = indexing.publish_snapshot
    def publish_then_fail(snapshot):
        publish(snapshot)
        raise OSError("failure after replace")
    monkeypatch.setattr(indexing, "publish_snapshot", publish_then_fail)
    with publication_db() as db:
        job = indexing.reindex_knowledge_documents(db=db)
        assert job.status == "running"
        assert db.get(KnowledgeDocument, "new-policy").index_dirty is True
    assert recover(publication_db) == 1
    assert ids() == {"old-policy", "new-policy"}


def test_failed_final_commit_is_retried_without_losing_the_live_version(publication_db, monkeypatch):
    with publication_db() as db:
        commit = db.commit
        failed = False
        def fail_final_once():
            nonlocal failed
            if not failed and any(isinstance(item, KnowledgeIndexJob) and item.status == "success" for item in db.identity_map.values()):
                failed = True
                raise RuntimeError("injected final commit failure")
            commit()
        monkeypatch.setattr(db, "commit", fail_final_once)
        assert indexing.reindex_knowledge_documents(db=db).status == "running"
        assert failed
    active = current_snapshot(default_index_root()).version
    assert recover(publication_db) == 1
    assert current_snapshot(default_index_root()).version == active


@pytest.mark.parametrize("damage", ["missing", "checksum", "context", "manifest"])
def test_recovery_rejects_invalid_published_candidate(publication_db, damage):
    crash(publication_db, "after_pointer")
    active = current_snapshot(default_index_root())
    if damage == "missing":
        (active.directory / "embedding_index.pkl").unlink()
    elif damage == "checksum":
        (active.directory / "bm25_documents.json").write_text("[]", encoding="utf-8")
    elif damage == "context":
        active.manifest.pop("publication")
        atomic_json(active.directory / "manifest.json", active.manifest)
    else:
        (active.directory / "manifest.json").unlink()
    assert recover(publication_db) == 1
    with publication_db() as db:
        assert latest(db).status == "failed"
        assert "校验失败" in latest(db).error_message
        assert db.get(KnowledgeDocument, "new-policy").index_dirty is True
    import json
    assert json.loads((default_index_root() / "current.json").read_text(encoding="utf-8"))["version"] == active.version


def test_next_publication_reconciles_interrupted_job_first(publication_db):
    crash(publication_db, "before_pointer")
    with publication_db() as db:
        previous_id = latest(db).id
        assert indexing.reindex_knowledge_documents(db=db).status == "success"
        assert db.get(KnowledgeIndexJob, previous_id).status == "failed"
    assert ids() == {"old-policy", "new-policy"}


def test_legacy_gap_restores_pending_without_invalidating_historical_success(publication_db):
    crash(publication_db, "before_pointer")
    with publication_db() as db:
        job = latest(db)
        job.status = "success"
        job.publication_phase = None
        candidate = snapshot_for_version(default_index_root(), job.index_version)
        candidate.manifest.pop("publication")
        atomic_json(candidate.directory / "manifest.json", candidate.manifest)
        job.index_version = None
        db.execute(update(KnowledgeDocument).values(index_dirty=False))
        db.commit()
    assert recover(publication_db) == 1
    with publication_db() as db:
        jobs = db.scalars(select(KnowledgeIndexJob).order_by(KnowledgeIndexJob.created_at)).all()
        assert [job.status for job in jobs] == ["success", "failed"]
        assert db.get(KnowledgeDocument, "new-policy").index_dirty is True
    assert ids() == {"old-policy"}


def test_legacy_gap_with_lost_source_restores_pending_conservatively(publication_db):
    crash(publication_db, "before_pointer")
    with publication_db() as db:
        job = latest(db)
        candidate = snapshot_for_version(default_index_root(), job.index_version)
        candidate.source.unlink()
        job.status = "success"
        job.publication_phase = None
        job.index_version = None
        db.execute(update(KnowledgeDocument).values(index_dirty=False))
        db.commit()
    assert recover(publication_db) == 1
    with publication_db() as db:
        assert latest(db).status == "failed"
        assert all(document.index_dirty for document in db.scalars(select(KnowledgeDocument)).all())
    assert ids() == {"old-policy"}


@pytest.mark.parametrize("damaged_file", ["current.json", "manifest.json"])
def test_non_object_json_is_rejected_during_recovery(publication_db, damaged_file):
    crash(publication_db, "after_pointer")
    active = current_snapshot(default_index_root())
    target = default_index_root() / damaged_file if damaged_file == "current.json" else active.directory / damaged_file
    target.write_text("[]", encoding="utf-8")
    assert recover(publication_db) == 1
    with publication_db() as db:
        assert latest(db).status == "failed"
        assert db.get(KnowledgeDocument, "new-policy").index_dirty is True


def test_superseded_legacy_successes_are_preserved(publication_db):
    with publication_db() as db:
        assert indexing.reindex_knowledge_documents(db=db).status == "success"
        db.execute(update(KnowledgeIndexJob).values(publication_phase=None, index_version=None))
        db.commit()
    assert recover(publication_db) == 1
    assert recover(publication_db) == 0
    with publication_db() as db:
        assert all(job.status == "success" for job in db.scalars(select(KnowledgeIndexJob)).all())
        assert db.get(KnowledgeDocument, "new-policy").index_dirty is False


def test_runtime_recovery_uses_its_own_database_session(publication_db, monkeypatch):
    crash(publication_db, "after_pointer")
    monkeypatch.setattr(recovery, "SessionLocal", publication_db)
    assert runtime_recovery() == 1


def test_application_startup_recovers_before_serving(publication_db, monkeypatch):
    from fastapi.testclient import TestClient
    from main import app

    crash(publication_db, "after_pointer")
    monkeypatch.setenv("SESSION_MEMORY_BACKEND", "ttlcache")
    monkeypatch.setattr(recovery, "SessionLocal", publication_db)
    monkeypatch.setattr(recovery, "recover_pending_knowledge_publications", runtime_recovery)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        with publication_db() as db:
            assert latest(db).status == "success"
            assert db.get(KnowledgeDocument, "new-policy").index_dirty is False


def test_surviving_worker_periodically_recovers_another_workers_crash(publication_db, monkeypatch):
    crash(publication_db, "after_pointer")
    monkeypatch.setattr(recovery, "SessionLocal", publication_db)
    finished = Event()
    def recover_and_signal():
        result = runtime_recovery()
        finished.set()
        return result
    monkeypatch.setattr(recovery, "recover_pending_knowledge_publications", recover_and_signal)
    async def exercise():
        task = asyncio.create_task(recovery.run_knowledge_publication_recovery(interval_seconds=0.01))
        try:
            assert await asyncio.to_thread(finished.wait, 10)
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
    asyncio.run(exercise())
    with publication_db() as db:
        assert latest(db).status == "success"


def test_recovery_retries_database_finalization_errors(publication_db, monkeypatch):
    crash(publication_db, "after_pointer")
    with publication_db() as db:
        commit = db.commit
        monkeypatch.setattr(db, "commit", lambda: (_ for _ in ()).throw(RuntimeError("DB unavailable")))
        with pytest.raises(RuntimeError, match="DB unavailable"):
            recovery.recover_knowledge_publications(db=db)
        db.rollback()
        monkeypatch.setattr(db, "commit", commit)
    with publication_db() as db:
        assert latest(db).status == "running"
    assert recover(publication_db) == 1


def test_recovery_keeps_restrictions_on_control_write_failure(publication_db, monkeypatch):
    with publication_db() as db:
        soft_delete_knowledge_document(db=db, knowledge_id="old-policy")
        update_knowledge_document_status(db=db, knowledge_id="old-policy", payload=KnowledgeDocumentStatusUpdate(is_active=True))
    crash(publication_db, "after_pointer")
    def fail_release(**kwargs):
        raise OSError("control write failure")
    monkeypatch.setattr(recovery, "release_published_restrictions", fail_release)
    assert recover(publication_db) == 1
    with publication_db() as db:
        assert latest(db).status == "success"
        assert "访问限制未解除" in latest(db).error_message
    assert ids() == {"new-policy"}


def test_metadata_recovery_uses_selected_api_database(api_session_factory, monkeypatch):
    """Runs against both SQLite and the PostgreSQL CI schema/session fixture."""
    monkeypatch.delenv("KNOWLEDGE_SOURCE_PATH", raising=False)
    with api_session_factory() as db:
        db.add(KnowledgeDocument(id="pg-policy", title="wind inspection", content="wind inspection guidance", knowledge_type="risk_advice", review_status="approved", is_active=True))
        db.commit()
        revision = db.get(KnowledgeDocument, "pg-policy").updated_at
    class AbruptExit(BaseException):
        pass
    def exit_before_finalization(**kwargs):
        raise AbruptExit()
    monkeypatch.setattr(indexing, "finish_published_job", exit_before_finalization)
    with api_session_factory() as db:
        with pytest.raises(AbruptExit):
            indexing.reindex_knowledge_documents(db=db)
    assert recover(api_session_factory) == 1
    assert recover(api_session_factory) == 0
    with api_session_factory() as db:
        document = db.get(KnowledgeDocument, "pg-policy")
        assert document.index_dirty is False
        assert document.updated_at == revision
        assert latest(db).status == "success"
