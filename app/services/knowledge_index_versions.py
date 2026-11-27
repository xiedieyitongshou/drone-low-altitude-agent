"""Immutable local index generations and a single atomic publication pointer.

All processes serving an index must share its directory. Old generations are
retained so that a reader which already selected one can finish safely.
"""

from __future__ import annotations

import hashlib
import json
import os
import pickle
import re
from contextlib import contextmanager
from contextvars import ContextVar
from copy import copy
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


class KnowledgeIndexBusyError(RuntimeError):
    pass


def filesystem_path(path: Path) -> Path:
    """Permit generation paths beyond MAX_PATH on Windows."""
    if os.name != "nt":
        return path
    absolute = str(path.resolve())
    if absolute.startswith("\\\\?\\"):
        return Path(absolute)
    if absolute.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + absolute[2:])
    return Path("\\\\?\\" + absolute)


@contextmanager
def index_lock(root: Path, name: str = "build"):
    """Nonblocking OS lock, released even if a builder process exits."""
    filesystem_path(root).mkdir(parents=True, exist_ok=True)
    with filesystem_path(root / f".{name}.lock").open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise KnowledgeIndexBusyError("知识索引正在更新，请稍后重试。") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_json(path: Path, payload: dict) -> None:
    path = filesystem_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class KnowledgeSnapshot:
    root: Path
    directory: Path
    manifest: dict

    @property
    def source(self) -> Path:
        return self.directory / "source.json"

    @property
    def version(self) -> str:
        return self.directory.name


_pinned: ContextVar[KnowledgeSnapshot | None] = ContextVar("knowledge_snapshot", default=None)


def current_snapshot(root: Path, pointer: str = "current.json") -> KnowledgeSnapshot | None:
    path = filesystem_path(root / pointer)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Invalid knowledge index publication pointer")
    version = data.get("version", "")
    return snapshot_for_version(root, version)


def snapshot_for_version(root: Path, version: str) -> KnowledgeSnapshot:
    if not isinstance(version, str) or not re.fullmatch(r"[a-z0-9]+-[0-9a-f]{32}", version):
        raise ValueError("Invalid knowledge index publication pointer")
    directory = filesystem_path(root / "versions" / version)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Invalid knowledge index publication manifest")
    return KnowledgeSnapshot(root=root, directory=directory, manifest=manifest)


def default_index_root() -> Path:
    from app.services import vector_knowledge_store

    return vector_knowledge_store.DEFAULT_DB_KNOWLEDGE_PATH.parent


def published_admin_source(root: Path) -> Path | None:
    snapshot = _pinned.get() or current_snapshot(root)
    if snapshot and snapshot.root.resolve() == root.resolve() and snapshot.manifest.get("origin") == "admin":
        return snapshot.source
    return None


@contextmanager
def pin_default_snapshot():
    existing = _pinned.get()
    if existing is not None:
        yield existing
        return
    snapshot = ensure_default_snapshot()
    token = _pinned.set(snapshot)
    try:
        yield snapshot
    finally:
        _pinned.reset(token)


def selected_default_snapshot() -> KnowledgeSnapshot:
    return _pinned.get() or ensure_default_snapshot()


def pinned_default_source() -> Path | None:
    snapshot = _pinned.get()
    return snapshot.source if snapshot else None


def _signature(store) -> dict:
    if hasattr(store, "provider"):
        from app.services.embedding_providers import provider_metadata

        return provider_metadata(store.provider)
    return {}


def _source_state(source: Path) -> dict:
    return {"source_path": str(source.resolve()), "source_mtime_ns": source.stat().st_mtime_ns}


def _same_source(snapshot: KnowledgeSnapshot, source: Path) -> bool:
    return snapshot.manifest.get("source_path") == str(source.resolve())


def _fresh(snapshot: KnowledgeSnapshot, source: Path, signature: dict) -> bool:
    return source.exists() and all(snapshot.manifest.get(key) == value for key, value in _source_state(source).items()) and snapshot.manifest.get("provider", {}) == signature


def bind_store(store, snapshot: KnowledgeSnapshot):
    bound = copy(store)
    bound.knowledge_path = snapshot.source
    bound.index_dir = snapshot.directory
    bound._snapshot = snapshot
    for attribute in ("index_path", "documents_path", "metadata_path", "vectorizer_path", "matrix_path"):
        if hasattr(store, attribute):
            setattr(bound, attribute, snapshot.directory / getattr(store, attribute).name)
    return bound


def store_snapshot(store, *, force: bool = False):
    if getattr(store, "_snapshot", None) is not None:
        if force:
            raise RuntimeError("已发布的知识索引不可覆盖，请构建新版本。")
        return store
    if store._default_location:
        return bind_store(store, ensure_default_snapshot(force=force))

    root = store.index_dir
    kind = store.index_kind
    pointer = f"{kind}-current.json"
    previous = current_snapshot(root, pointer)
    signature = _signature(store)
    if not force and previous and _fresh(previous, store.knowledge_path, signature):
        return bind_store(store, previous)
    try:
        with index_lock(root):
            previous = current_snapshot(root, pointer)
            if not force and previous and _fresh(previous, store.knowledge_path, signature):
                return bind_store(store, previous)
            snapshot = prepare_snapshot(root, source=store.knowledge_path, origin=kind, provider=signature)
            bound = bind_store(store, snapshot)
            count = bound._build_index()
            validate_index(snapshot, kind)
            complete_snapshot(snapshot, {"count": count})
            publish_snapshot(snapshot, pointer)
            return bound
    except (OSError, ValueError, RuntimeError, EOFError, pickle.UnpicklingError):
        # Explicit rebuilds report failure. Queries can keep a previously valid
        # generation, but never substitute another source or embedding model.
        if not force and previous and _same_source(previous, store.knowledge_path) and previous.manifest.get("provider", {}) == signature:
            return bind_store(store, previous)
        raise


def prepare_snapshot(root: Path, *, source: Path | None = None, library=None, origin: str, provider: dict | None = None) -> KnowledgeSnapshot:
    directory = filesystem_path(root / "versions" / f"{origin}-{uuid4().hex}")
    directory.mkdir(parents=True)
    manifest = {"origin": origin, "provider": provider or {}}
    if library is not None:
        content = json.dumps(library.model_dump(mode="json"), ensure_ascii=False, indent=2).encode("utf-8")
    else:
        manifest.update(_source_state(source))
        content = source.read_bytes()
    from app.schemas.advice import KnowledgeAdviceLibrary

    KnowledgeAdviceLibrary.model_validate_json(content.decode("utf-8-sig"))
    (directory / "source.json").write_bytes(content)
    manifest["source_sha256"] = hashlib.sha256(content).hexdigest()
    return KnowledgeSnapshot(root=root, directory=directory, manifest=manifest)


def complete_snapshot(snapshot: KnowledgeSnapshot, extra: dict | None = None) -> None:
    snapshot.manifest.update(extra or {})
    snapshot.manifest["files"] = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in snapshot.directory.iterdir() if path.is_file() and path.name != "manifest.json"
    }
    # Flush every artifact before making the generation visible.
    for path in snapshot.directory.iterdir():
        if path.is_file():
            with path.open("r+b") as handle:
                os.fsync(handle.fileno())
    atomic_json(snapshot.directory / "manifest.json", snapshot.manifest)


def publish_snapshot(snapshot: KnowledgeSnapshot, pointer: str = "current.json") -> None:
    atomic_json(snapshot.root / pointer, {"version": snapshot.version})


def validate_index(snapshot: KnowledgeSnapshot, kind: str) -> None:
    from app.schemas.advice import KnowledgeAdviceLibrary
    from app.services.knowledge_chunker import build_indexed_chunks
    from app.services.vector_knowledge_store import build_indexed_documents

    library = KnowledgeAdviceLibrary.model_validate_json(snapshot.source.read_text(encoding="utf-8-sig"))
    directory = snapshot.directory
    if kind in {"bm25", "embedding"}:
        expected = [chunk.__dict__ for chunk in build_indexed_chunks(library)]
        documents = json.loads((directory / f"{kind}_documents.json").read_text(encoding="utf-8"))
        if documents != expected:
            raise ValueError(f"{kind} documents do not match the source")
        with (directory / f"{kind}_index.pkl").open("rb") as handle:
            index = pickle.load(handle)
        if kind == "bm25":
            if not all(len(values) == len(expected) for values in (index.doc_tokens, index.doc_term_freqs, index.doc_lengths)):
                raise ValueError("BM25 index/document count mismatch")
        else:
            metadata = json.loads((directory / "embedding_metadata.json").read_text(encoding="utf-8"))
            if len(index.embeddings) != len(expected) or metadata != index.metadata:
                raise ValueError("Embedding index/document metadata mismatch")
            if any(len(vector) != metadata["dimension"] for vector in index.embeddings):
                raise ValueError("Embedding dimension mismatch")
    else:
        expected = [document.__dict__ for document in build_indexed_documents(library)]
        documents = json.loads((directory / "documents.json").read_text(encoding="utf-8"))
        with (directory / "tfidf_matrix.pkl").open("rb") as handle:
            matrix = pickle.load(handle)
        with (directory / "tfidf_vectorizer.pkl").open("rb") as handle:
            vectorizer = pickle.load(handle)
        if documents != expected or (len(expected) and (matrix.shape[0] != len(expected) or matrix.shape[1] != len(vectorizer.vocabulary_))):
            raise ValueError("TF-IDF index/document mismatch")
        if not expected and (matrix is not None or vectorizer is not None):
            raise ValueError("Empty TF-IDF index must be empty")


def build_bundle(snapshot: KnowledgeSnapshot) -> None:
    from app.services.bm25_knowledge_store import LocalBm25KnowledgeStore
    from app.services.embedding_knowledge_store import LocalEmbeddingKnowledgeStore
    from app.services.vector_knowledge_store import LocalVectorKnowledgeStore

    for cls in (LocalBm25KnowledgeStore, LocalEmbeddingKnowledgeStore, LocalVectorKnowledgeStore):
        store = bind_store(cls(knowledge_path=snapshot.source, index_dir=snapshot.directory), snapshot)
        store._build_index()
        validate_index(snapshot, store.index_kind)
    complete_snapshot(snapshot)


def validate_bundle(snapshot: KnowledgeSnapshot) -> None:
    """Check durable artifacts before recovery trusts a published generation."""
    required = {
        "source.json", "bm25_index.pkl", "bm25_documents.json",
        "embedding_index.pkl", "embedding_documents.json", "embedding_metadata.json",
        "tfidf_vectorizer.pkl", "tfidf_matrix.pkl", "documents.json",
    }
    files = snapshot.manifest.get("files")
    if not isinstance(files, dict) or not required.issubset(files):
        raise ValueError("Incomplete knowledge publication manifest")
    for name, expected in files.items():
        if not isinstance(name, str) or Path(name).name != name or name in {".", ".."}:
            raise ValueError("Invalid knowledge publication artifact")
        if hashlib.sha256((snapshot.directory / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Knowledge publication checksum mismatch: {name}")
    if files["source.json"] != snapshot.manifest.get("source_sha256"):
        raise ValueError("Knowledge publication source checksum mismatch")
    for kind in ("bm25", "embedding", "tfidf"):
        validate_index(snapshot, kind)


def ensure_default_snapshot(*, force: bool = False) -> KnowledgeSnapshot:
    from app.services.vector_knowledge_store import get_default_knowledge_path

    if not force and _pinned.get() is not None:
        return _pinned.get()
    root = default_index_root()
    previous = current_snapshot(root)
    source = get_default_knowledge_path()
    if previous and source.resolve() == previous.source.resolve():
        if force:
            raise RuntimeError("数据库知识请通过管理员发布入口更新。")
        return previous
    if not force and previous and _fresh(previous, source, {}):
        return previous
    try:
        with index_lock(root):
            previous = current_snapshot(root)
            if not force and previous and _fresh(previous, source, {}):
                return previous
            snapshot = prepare_snapshot(root, source=source, origin="static")
            build_bundle(snapshot)
            publish_snapshot(snapshot)
            return snapshot
    except (OSError, ValueError, RuntimeError, EOFError, pickle.UnpicklingError):
        if not force and previous and _same_source(previous, source):
            return previous
        raise
