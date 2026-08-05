import json
import math
import pickle
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.schemas.advice import (
    KnowledgeAccessContext,
    KnowledgeAdviceLibrary,
    KnowledgeBusinessContext,
    RetrievedKnowledgeSnippet,
)
from app.services.vector_knowledge_store import (
    DEFAULT_INDEX_DIR,
    DEFAULT_KNOWLEDGE_PATH,
    is_document_applicable,
    is_document_visible,
)
from app.services.knowledge_chunker import IndexedKnowledgeChunk, build_indexed_chunks
from app.services.knowledge_reranker import rule_rerank_boost


BM25_K1 = 1.5
BM25_B = 0.75
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


@dataclass
class Bm25Index:
    doc_tokens: list[list[str]]
    doc_term_freqs: list[dict[str, int]]
    doc_lengths: list[int]
    avg_doc_length: float
    idf: dict[str, float]


class LocalBm25KnowledgeStore:
    """Lightweight BM25 index for keyword-oriented knowledge retrieval."""

    def __init__(self, *, knowledge_path: Path | None = None, index_dir: Path | None = None) -> None:
        self.knowledge_path = knowledge_path or DEFAULT_KNOWLEDGE_PATH
        self.index_dir = index_dir or DEFAULT_INDEX_DIR
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.index_dir / "bm25_index.pkl"
        self.documents_path = self.index_dir / "bm25_documents.json"

    def build_index(self) -> int:
        library = self._load_library()
        chunks = build_indexed_chunks(library)
        doc_tokens = [_tokenize_chunk(chunk) for chunk in chunks]
        doc_term_freqs = [dict(Counter(tokens)) for tokens in doc_tokens]
        doc_lengths = [len(tokens) for tokens in doc_tokens]
        avg_doc_length = sum(doc_lengths) / len(doc_lengths) if doc_lengths else 0.0
        document_frequency = _document_frequency(doc_tokens)
        idf = {
            term: math.log(1 + (len(chunks) - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }
        index = Bm25Index(
            doc_tokens=doc_tokens,
            doc_term_freqs=doc_term_freqs,
            doc_lengths=doc_lengths,
            avg_doc_length=avg_doc_length,
            idf=idf,
        )

        with self.index_path.open("wb") as file:
            pickle.dump(index, file)
        self.documents_path.write_text(
            json.dumps([chunk.__dict__ for chunk in chunks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
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
        query_tokens = tokenize_text(query_text)
        if not query_tokens:
            return []

        scored_chunks: list[tuple[float, float, IndexedKnowledgeChunk]] = []
        for chunk_index, chunk in enumerate(chunks):
            if not is_document_visible(chunk.metadata, access_context):
                continue
            if not is_document_applicable(chunk.metadata, business_context):
                continue

            score = _bm25_score(
                query_tokens=query_tokens,
                term_freqs=index.doc_term_freqs[chunk_index],
                doc_length=index.doc_lengths[chunk_index],
                avg_doc_length=index.avg_doc_length,
                idf=index.idf,
            )
            if score <= 0:
                continue
            rerank_boost = rule_rerank_boost(chunk.metadata, business_context)
            scored_chunks.append((score * (1 + rerank_boost * 0.05), rerank_boost, chunk))

        scored_chunks.sort(key=lambda item: (-item[0], -item[1], item[2].title))
        return [
            RetrievedKnowledgeSnippet(
                id=chunk.knowledge_id,
                title=chunk.title,
                content=chunk.content,
                score=round(score, 6),
                source=chunk.source,
                source_url=chunk.source_url,
                metadata={**chunk.metadata, "retriever": "bm25", "rerank_boost": round(rerank_boost, 6)},
            )
            for score, rerank_boost, chunk in scored_chunks[:top_k]
        ]

    def _ensure_index(self) -> None:
        if not self.index_path.exists() or not self.documents_path.exists():
            self.build_index()
            return
        if self.knowledge_path.exists():
            source_mtime = self.knowledge_path.stat().st_mtime
            index_mtime = self.documents_path.stat().st_mtime
            if source_mtime > index_mtime:
                self.build_index()

    def _load_index(self) -> Bm25Index:
        with self.index_path.open("rb") as file:
            return pickle.load(file)

    def _load_library(self) -> KnowledgeAdviceLibrary:
        payload = json.loads(self.knowledge_path.read_text(encoding="utf-8-sig"))
        return KnowledgeAdviceLibrary.model_validate(payload)


def tokenize_text(text: str) -> list[str]:
    raw_tokens = [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text)]
    tokens: list[str] = []
    chinese_buffer: list[str] = []

    def flush_chinese_buffer() -> None:
        if not chinese_buffer:
            return
        tokens.extend(chinese_buffer)
        if len(chinese_buffer) >= 2:
            tokens.extend("".join(chinese_buffer[index : index + 2]) for index in range(len(chinese_buffer) - 1))
        if len(chinese_buffer) >= 3:
            tokens.extend("".join(chinese_buffer[index : index + 3]) for index in range(len(chinese_buffer) - 2))
        chinese_buffer.clear()

    for token in raw_tokens:
        if _is_chinese_char(token):
            chinese_buffer.append(token)
            continue
        flush_chinese_buffer()
        tokens.append(token)

    flush_chinese_buffer()
    return tokens


def _tokenize_chunk(chunk: IndexedKnowledgeChunk) -> list[str]:
    keywords = chunk.metadata.get("keywords")
    keyword_text = " ".join(str(item) for item in keywords) if isinstance(keywords, list) else ""
    return tokenize_text(f"{chunk.title}\n{chunk.content}\n{keyword_text}")


def _document_frequency(doc_tokens: list[list[str]]) -> dict[str, int]:
    frequencies: Counter[str] = Counter()
    for tokens in doc_tokens:
        frequencies.update(set(tokens))
    return dict(frequencies)


def _bm25_score(
    *,
    query_tokens: list[str],
    term_freqs: dict[str, int],
    doc_length: int,
    avg_doc_length: float,
    idf: dict[str, float],
) -> float:
    if doc_length <= 0 or avg_doc_length <= 0:
        return 0.0

    score = 0.0
    for term in set(query_tokens):
        term_frequency = term_freqs.get(term, 0)
        if term_frequency <= 0:
            continue
        denominator = term_frequency + BM25_K1 * (1 - BM25_B + BM25_B * doc_length / avg_doc_length)
        score += idf.get(term, 0.0) * term_frequency * (BM25_K1 + 1) / denominator
    return score


def _is_chinese_char(value: str) -> bool:
    return len(value) == 1 and "\u4e00" <= value <= "\u9fff"

