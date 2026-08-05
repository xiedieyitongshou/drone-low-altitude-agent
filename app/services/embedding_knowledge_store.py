import json
import os
import pickle
import time
from dataclasses import dataclass
from pathlib import Path

from app.schemas.advice import (
    KnowledgeAccessContext,
    KnowledgeAdviceLibrary,
    KnowledgeBusinessContext,
    RetrievedKnowledgeSnippet,
)
from app.services.embedding_providers import (
    EmbeddingProvider,
    MockEmbeddingProvider,
    cosine_similarity,
    provider_metadata,
)
from app.services.knowledge_chunker import IndexedKnowledgeChunk, build_indexed_chunks
from app.services.knowledge_reranker import rule_rerank_boost
from app.services.vector_knowledge_store import (
    DEFAULT_INDEX_DIR,
    DEFAULT_KNOWLEDGE_PATH,
    is_document_applicable,
    is_document_visible,
)


DEFAULT_EMBEDDING_MIN_SCORE = 0.25


@dataclass
class EmbeddingIndex:
    embeddings: list[list[float]]
    metadata: dict[str, object]


class LocalEmbeddingKnowledgeStore:
    """Local embedding index with provider metadata validation."""

    def __init__(
        self,
        *,
        provider: EmbeddingProvider | None = None,
        knowledge_path: Path | None = None,
        index_dir: Path | None = None,
        min_score: float | None = None,
    ) -> None:
        self.provider = provider or MockEmbeddingProvider()
        self.knowledge_path = knowledge_path or DEFAULT_KNOWLEDGE_PATH
        self.index_dir = index_dir or DEFAULT_INDEX_DIR
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.index_dir / "embedding_index.pkl"
        self.documents_path = self.index_dir / "embedding_documents.json"
        self.metadata_path = self.index_dir / "embedding_metadata.json"
        self.min_score = min_score if min_score is not None else _load_min_score()

    def build_index(self) -> int:
        library = self._load_library()
        chunks = build_indexed_chunks(library)
        embeddings = self.provider.embed_texts([_embedding_chunk_text(chunk) for chunk in chunks])
        metadata = self._expected_metadata()
        index = EmbeddingIndex(embeddings=embeddings, metadata=metadata)

        with self.index_path.open("wb") as file:
            pickle.dump(index, file)
        self.documents_path.write_text(
            json.dumps([chunk.__dict__ for chunk in chunks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        return len(chunks)

    def retrieve(
        self,
        query_text: str,
        *,
        top_k: int = 5,
        access_context: KnowledgeAccessContext | None = None,
        business_context: KnowledgeBusinessContext | None = None,
    ) -> list[RetrievedKnowledgeSnippet]:
        self._ensure_index()
        index = self._load_index()
        chunks = [
            IndexedKnowledgeChunk(**item)
            for item in json.loads(self.documents_path.read_text(encoding="utf-8-sig"))
        ]
        query_embedding = self.provider.embed_texts([query_text])[0]
        if not query_embedding:
            return []

        scored_chunks: list[tuple[float, float, IndexedKnowledgeChunk]] = []
        for chunk, embedding in zip(chunks, index.embeddings, strict=False):
            if not is_document_visible(chunk.metadata, access_context):
                continue
            if not is_document_applicable(chunk.metadata, business_context):
                continue

            score = cosine_similarity(query_embedding, embedding)
            if score < self.min_score:
                continue
            rerank_boost = rule_rerank_boost(chunk.metadata, business_context)
            scored_chunks.append((score * (1 + rerank_boost * 0.05), rerank_boost, chunk))

        scored_chunks.sort(key=lambda item: (-item[0], -item[1], item[2].title))
        retriever_metadata = {
            "retriever": "embedding",
            "embedding_provider": self.provider.name,
            "embedding_model": self.provider.model,
            "embedding_dimension": self.provider.dimension,
            "min_score": self.min_score,
        }
        return [
            RetrievedKnowledgeSnippet(
                id=chunk.knowledge_id,
                title=chunk.title,
                content=chunk.content,
                score=round(score, 6),
                source=chunk.source,
                source_url=chunk.source_url,
                metadata={**chunk.metadata, **retriever_metadata, "rerank_boost": round(rerank_boost, 6)},
            )
            for score, rerank_boost, chunk in scored_chunks[:top_k]
        ]

    def _ensure_index(self) -> None:
        if not self.index_path.exists() or not self.documents_path.exists() or not self.metadata_path.exists():
            self.build_index()
            return
        metadata = json.loads(self.metadata_path.read_text(encoding="utf-8-sig"))
        if self._metadata_mismatch(metadata) or self._source_is_newer_than_index(metadata):
            self.build_index()

    def _load_index(self) -> EmbeddingIndex:
        with self.index_path.open("rb") as file:
            return pickle.load(file)

    def _load_library(self) -> KnowledgeAdviceLibrary:
        payload = json.loads(self.knowledge_path.read_text(encoding="utf-8-sig"))
        return KnowledgeAdviceLibrary.model_validate(payload)

    def _expected_metadata(self) -> dict[str, object]:
        return {
            **provider_metadata(self.provider),
            "knowledge_path": str(self.knowledge_path),
            "knowledge_mtime": self.knowledge_path.stat().st_mtime if self.knowledge_path.exists() else None,
            "created_at": int(time.time()),
        }

    def _metadata_mismatch(self, metadata: dict[str, object]) -> bool:
        expected = provider_metadata(self.provider)
        return any(metadata.get(key) != value for key, value in expected.items())

    def _source_is_newer_than_index(self, metadata: dict[str, object]) -> bool:
        if not self.knowledge_path.exists():
            return False
        indexed_mtime = metadata.get("knowledge_mtime")
        if not isinstance(indexed_mtime, (int, float)):
            return True
        return self.knowledge_path.stat().st_mtime > indexed_mtime


def _embedding_chunk_text(chunk: IndexedKnowledgeChunk) -> str:
    keywords = chunk.metadata.get("keywords")
    keyword_text = " ".join(str(item) for item in keywords) if isinstance(keywords, list) else ""
    return f"{chunk.title}\n{chunk.content}\n{keyword_text}"


def _load_min_score() -> float:
    raw_value = os.getenv("KNOWLEDGE_EMBEDDING_MIN_SCORE")
    if raw_value is None:
        return DEFAULT_EMBEDDING_MIN_SCORE
    try:
        return float(raw_value)
    except ValueError:
        return DEFAULT_EMBEDDING_MIN_SCORE
