import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import KnowledgeDocument
from app.schemas.advice import KnowledgeAccessContext, KnowledgeRetrievalRequest
from app.schemas.knowledge import KnowledgeDocumentStatusUpdate, KnowledgeDocumentUpdate
from app.services import admin_knowledge_indexing as indexing
from app.services.admin_knowledge_management import (
    soft_delete_knowledge_document, update_knowledge_document, update_knowledge_document_status,
)
from app.services.advice_retriever import retrieve_knowledge_by_request
from app.services.bm25_knowledge_store import LocalBm25KnowledgeStore
from app.services.embedding_knowledge_store import LocalEmbeddingKnowledgeStore
from app.services.knowledge_index_versions import (
    KnowledgeIndexBusyError, current_snapshot, default_index_root, index_lock, store_snapshot,
)
from app.services.knowledge_retrievers import create_default_knowledge_retriever
from app.services.knowledge_runtime_control import (
    read_control, set_retrieval_maintenance, sanitize_composed_knowledge,
)
from app.services.vector_knowledge_store import LocalVectorKnowledgeStore


@pytest.fixture
def knowledge_db(tmp_path, monkeypatch):
    monkeypatch.delenv("KNOWLEDGE_SOURCE_PATH", raising=False)
    monkeypatch.setenv("KNOWLEDGE_RETRIEVER", "hybrid")
    monkeypatch.setenv("LLM_ENABLED", "false")
    engine = create_engine(f"sqlite:///{(tmp_path / 'publication.db').as_posix()}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(KnowledgeDocument(
            id="wind-policy", title="wind inspection policy", content="wind inspection policy original guidance",
            knowledge_type="risk_advice", review_status="approved", is_active=True,
        ))
        db.commit()
        job = indexing.reindex_knowledge_documents(db=db)
        assert job.status == "success", job.error_message
    yield factory
    engine.dispose()


def _publish(factory):
    with factory() as db:
        return indexing.reindex_knowledge_documents(db=db)


def _add(factory, document_id="new-policy"):
    with factory() as db:
        db.add(KnowledgeDocument(
            id=document_id, title="wind inspection addition", content="wind inspection additional guidance",
            knowledge_type="risk_advice", review_status="approved", is_active=True,
        ))
        db.commit()


def _ids():
    return {item.id for item in create_default_knowledge_retriever().retrieve("wind inspection", top_k=10)}


def test_query_keeps_one_version_when_publish_occurs_between_index_and_documents(knowledge_db, monkeypatch):
    reader = create_default_knowledge_retriever()
    old_version = reader.bm25_store._snapshot.version
    _add(knowledge_db)
    loaded, resume = Event(), Event()
    original = LocalBm25KnowledgeStore._load_index

    def pause_after_load(store):
        index = original(store)
        loaded.set()
        assert resume.wait(10)
        return index

    with ThreadPoolExecutor(max_workers=1) as pool:
        monkeypatch.setattr(LocalBm25KnowledgeStore, "_load_index", pause_after_load)
        query = pool.submit(reader.retrieve, "wind inspection", top_k=10)
        assert loaded.wait(10)
        try:
            assert _publish(knowledge_db).status == "success"
        finally:
            resume.set()
        results = query.result(timeout=10)
    assert {item.id for item in results} == {"wind-policy"}
    assert {item.metadata["index_version"] for item in results} == {old_version}
    assert _ids() == {"wind-policy", "new-policy"}


def test_queries_continue_using_old_version_during_construction(knowledge_db, monkeypatch):
    _add(knowledge_db)
    started, resume = Event(), Event()
    original = indexing._build_retrieval_indexes

    def paused_build(snapshot):
        started.set()
        assert resume.wait(10)
        original(snapshot)

    monkeypatch.setattr(indexing, "_build_retrieval_indexes", paused_build)
    with ThreadPoolExecutor(max_workers=1) as pool:
        build = pool.submit(_publish, knowledge_db)
        assert started.wait(10)
        try:
            assert _ids() == {"wind-policy"}
        finally:
            resume.set()
        assert build.result(timeout=10).status == "success"
    assert _ids() == {"wind-policy", "new-policy"}


def test_partial_build_failure_does_not_publish_any_artifact(knowledge_db, monkeypatch):
    root = default_index_root()
    old = current_snapshot(root)
    old_files = {path.name: path.read_bytes() for path in old.directory.iterdir()}
    _add(knowledge_db)

    def fail_embedding(store):
        store.index_path.write_bytes(b"incomplete")
        raise RuntimeError("injected embedding failure")

    monkeypatch.setattr(LocalEmbeddingKnowledgeStore, "_build_index", fail_embedding)
    job = _publish(knowledge_db)
    assert job.status == "failed"
    assert current_snapshot(root).version == old.version
    assert old_files == {path.name: path.read_bytes() for path in old.directory.iterdir()}
    assert _ids() == {"wind-policy"}
    with knowledge_db() as db:
        assert db.get(KnowledgeDocument, "new-policy").index_dirty is True


def test_validation_rejects_mismatched_artifacts(knowledge_db, monkeypatch):
    old = current_snapshot(default_index_root()).version
    original = LocalEmbeddingKnowledgeStore._build_index

    def mismatched(store):
        count = original(store)
        store.documents_path.write_text("[]", encoding="utf-8")
        return count

    monkeypatch.setattr(LocalEmbeddingKnowledgeStore, "_build_index", mismatched)
    assert _publish(knowledge_db).status == "failed"
    assert current_snapshot(default_index_root()).version == old


def test_pointer_write_failure_keeps_old_version_and_pending_changes(knowledge_db, monkeypatch):
    from app.services import knowledge_index_versions

    old = current_snapshot(default_index_root()).version
    _add(knowledge_db)
    original = knowledge_index_versions.atomic_json

    def fail_pointer(path, payload):
        if path.name == "current.json":
            raise OSError("injected pointer failure")
        original(path, payload)

    monkeypatch.setattr(knowledge_index_versions, "atomic_json", fail_pointer)
    assert _publish(knowledge_db).status == "failed"
    assert current_snapshot(default_index_root()).version == old
    with knowledge_db() as db:
        assert db.get(KnowledgeDocument, "new-policy").index_dirty is True


def test_edit_during_build_remains_pending_and_query_can_finish_on_old_version(knowledge_db, monkeypatch):
    old_reader = create_default_knowledge_retriever()
    original = indexing._build_retrieval_indexes

    def edit_while_building(snapshot):
        with knowledge_db() as db:
            update_knowledge_document(db=db, knowledge_id="wind-policy", payload=KnowledgeDocumentUpdate(content="wind inspection later edit"))
        original(snapshot)

    monkeypatch.setattr(indexing, "_build_retrieval_indexes", edit_while_building)
    assert _publish(knowledge_db).status == "success"
    assert old_reader.retrieve("wind inspection", top_k=5)
    with knowledge_db() as db:
        assert db.get(KnowledgeDocument, "wind-policy").index_dirty is True
    results = create_default_knowledge_retriever().retrieve("wind inspection", top_k=5)
    assert all("original guidance" in item.content for item in results)


def test_concurrent_builds_are_rejected_across_threads_and_processes(knowledge_db):
    root = default_index_root()
    with index_lock(root):
        with pytest.raises(KnowledgeIndexBusyError):
            _publish(knowledge_db)
        result = subprocess.run([
            sys.executable, "-c",
            "from pathlib import Path; from app.services.knowledge_index_versions import index_lock; "
            "import sys\ntry:\n with index_lock(Path(sys.argv[1])): print('acquired')\n"
            "except RuntimeError: print('busy')",
            str(root),
        ], capture_output=True, text=True, timeout=15, check=True)
        assert result.stdout.strip() == "busy"
    assert _publish(knowledge_db).status == "success"


def test_process_exit_releases_build_lock(knowledge_db):
    root = default_index_root()
    subprocess.run([
        sys.executable, "-c",
        "from pathlib import Path; from app.services.knowledge_index_versions import index_lock; "
        "import sys, os\nwith index_lock(Path(sys.argv[1])): os._exit(0)", str(root),
    ], timeout=15, check=True)
    assert _publish(knowledge_db).status == "success"


def test_ordinary_edit_stays_unpublished_until_successful_switch(knowledge_db):
    old = current_snapshot(default_index_root()).version
    with knowledge_db() as db:
        update_knowledge_document(db=db, knowledge_id="wind-policy", payload=KnowledgeDocumentUpdate(content="wind inspection corrected guidance"))
    results = create_default_knowledge_retriever().retrieve("wind inspection", top_k=5)
    assert all("original guidance" in item.content for item in results)
    assert current_snapshot(default_index_root()).version == old
    assert _publish(knowledge_db).status == "success"
    results = create_default_knowledge_retriever().retrieve("wind inspection", top_k=5)
    assert all("corrected guidance" in item.content for item in results)


def test_withdrawal_survives_failed_build_and_reenable_requires_publication(knowledge_db, monkeypatch):
    _add(knowledge_db)
    assert _publish(knowledge_db).status == "success"
    old_reader = create_default_knowledge_retriever()
    with knowledge_db() as db:
        soft_delete_knowledge_document(db=db, knowledge_id="wind-policy")
    assert _ids() == {"new-policy"}
    assert {item.id for item in old_reader.retrieve("wind inspection", top_k=10)} == {"new-policy"}
    original = indexing._build_retrieval_indexes
    monkeypatch.setattr(indexing, "_build_retrieval_indexes", lambda _: (_ for _ in ()).throw(RuntimeError("failure")))
    assert _publish(knowledge_db).status == "failed"
    assert _ids() == {"new-policy"}
    with knowledge_db() as db:
        update_knowledge_document_status(db=db, knowledge_id="wind-policy", payload=KnowledgeDocumentStatusUpdate(is_active=True))
    assert _ids() == {"new-policy"}
    monkeypatch.setattr(indexing, "_build_retrieval_indexes", original)
    assert _publish(knowledge_db).status == "success"
    assert _ids() == {"wind-policy", "new-policy"}
    # Corrected publication must never reopen the withdrawn older generation.
    assert {item.id for item in old_reader.retrieve("wind inspection", top_k=10)} == {"new-policy"}


def test_withdrawal_during_build_cannot_be_cleared_by_publication(knowledge_db, monkeypatch):
    original = indexing._build_retrieval_indexes

    def withdraw_while_building(snapshot):
        with knowledge_db() as db:
            soft_delete_knowledge_document(db=db, knowledge_id="wind-policy")
        original(snapshot)

    monkeypatch.setattr(indexing, "_build_retrieval_indexes", withdraw_while_building)
    assert _publish(knowledge_db).status == "success"
    assert _ids() == set()
    assert read_control()["documents"]["wind-policy"]["blocked"] is True
    with knowledge_db() as db:
        assert db.get(KnowledgeDocument, "wind-policy").index_dirty is True


def test_failed_withdrawal_database_commit_does_not_reopen_old_content(knowledge_db, monkeypatch):
    with knowledge_db() as db:
        monkeypatch.setattr(db, "commit", lambda: (_ for _ in ()).throw(RuntimeError("commit failure")))
        with pytest.raises(RuntimeError):
            soft_delete_knowledge_document(db=db, knowledge_id="wind-policy")
        db.rollback()
    assert _ids() == set()
    assert _publish(knowledge_db).status == "success"
    assert _ids() == set()
    assert read_control()["documents"]["wind-policy"]["blocked"] is True


def test_failed_permission_change_cannot_be_cleared_by_publishing_old_database_values(knowledge_db, monkeypatch):
    with knowledge_db() as db:
        monkeypatch.setattr(db, "commit", lambda: (_ for _ in ()).throw(RuntimeError("commit failure")))
        with pytest.raises(RuntimeError):
            update_knowledge_document(db=db, knowledge_id="wind-policy", payload=KnowledgeDocumentUpdate(visibility="private", user_id="owner"))
        db.rollback()
    assert _ids() == set()
    assert _publish(knowledge_db).status == "success"
    assert _ids() == set()


def test_permission_tightening_is_immediate_and_widening_waits_for_publication(knowledge_db):
    with knowledge_db() as db:
        update_knowledge_document(db=db, knowledge_id="wind-policy", payload=KnowledgeDocumentUpdate(visibility="private", user_id="owner"))
    reader = create_default_knowledge_retriever()
    owner = KnowledgeAccessContext(user_id="owner")
    assert reader.retrieve("wind inspection", top_k=5) == []
    assert reader.retrieve("wind inspection", top_k=5, access_context=owner)
    with knowledge_db() as db:
        update_knowledge_document(db=db, knowledge_id="wind-policy", payload=KnowledgeDocumentUpdate(visibility="public", user_id=None))
    assert _ids() == set()
    assert _publish(knowledge_db).status == "success"
    assert _ids() == {"wind-policy"}


def test_global_pause_survives_both_successful_and_failed_publication(knowledge_db, monkeypatch):
    set_retrieval_maintenance(paused=True, message="知识库维护中", actor="admin")
    response = retrieve_knowledge_by_request(KnowledgeRetrievalRequest(task_type="inspection", query="wind inspection"))
    assert response.retrieval_status == "maintenance"
    assert response.retrieval_message == "知识库维护中"
    assert response.snippets == response.advice == []
    assert _ids() == set()
    assert _publish(knowledge_db).status == "success"
    assert read_control()["paused"] is True
    monkeypatch.setattr(indexing, "_build_retrieval_indexes", lambda _: (_ for _ in ()).throw(RuntimeError("failure")))
    assert _publish(knowledge_db).status == "failed"
    assert read_control()["paused"] is True
    set_retrieval_maintenance(paused=False, actor="admin")
    assert _ids() == {"wind-policy"}


@pytest.mark.parametrize("action", ["withdraw", "pause"])
def test_pause_and_withdrawal_are_rechecked_after_llm_review(knowledge_db, monkeypatch, action):
    from app.services import advice_retriever

    def revoke_during_review(query, snippets, business_context):
        if action == "withdraw":
            with knowledge_db() as db:
                soft_delete_knowledge_document(db=db, knowledge_id="wind-policy")
        else:
            set_retrieval_maintenance(paused=True)
        return snippets, [], "accepted"

    monkeypatch.setattr(advice_retriever, "assess_candidate_relevance", revoke_during_review)
    response = retrieve_knowledge_by_request(KnowledgeRetrievalRequest(task_type="inspection", query="wind inspection"))
    assert response.snippets == []
    assert response.retrieval_status == ("fallback" if action == "withdraw" else "maintenance")


def test_explanation_using_revoked_knowledge_is_discarded(knowledge_db):
    from app.schemas.composed_response import UnifiedBusinessResponse

    response = UnifiedBusinessResponse(
        scene="evaluate", summary="rule result", explanation="revoked advice from LLM", explanation_source="llm", llm_used=True,
        details={"knowledge_snippets": [{"id": "wind-policy", "content": "original guidance"}], "advice": []},
    )
    with knowledge_db() as db:
        soft_delete_knowledge_document(db=db, knowledge_id="wind-policy")
    assert sanitize_composed_knowledge(response)
    assert response.details["knowledge_snippets"] == []
    assert response.explanation_source == "template"
    assert "revoked advice from LLM" not in response.explanation


@pytest.mark.parametrize("cls", [LocalBm25KnowledgeStore, LocalEmbeddingKnowledgeStore, LocalVectorKnowledgeStore])
def test_query_auto_rebuild_failure_keeps_its_last_valid_generation(tmp_path, monkeypatch, cls):
    source = tmp_path / "source.json"
    payload = {"version": "1", "items": [{"id": "first", "category": "risk_advice", "title": "wind inspection", "advice_text": "wind inspection guidance", "priority": "medium"}]}
    source.write_text(json.dumps(payload), encoding="utf-8")
    store = cls(knowledge_path=source, index_dir=tmp_path / "indexes")
    store.build_index()
    old = store_snapshot(store)._snapshot.version
    payload["items"].append({**payload["items"][0], "id": "second"})
    source.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(cls, "_build_index", lambda _: (_ for _ in ()).throw(RuntimeError("failure")))
    results = store.retrieve("wind inspection", top_k=5)
    assert {item.id for item in results} == {"first"}
    assert {item.metadata["index_version"] for item in results} == {old}
