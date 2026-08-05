import hashlib
import math
from dataclasses import dataclass
from typing import Protocol

from app.services.bm25_knowledge_store import tokenize_text


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dimension: int

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...


@dataclass(frozen=True)
class MockEmbeddingProvider:
    """Deterministic local embedding provider for offline demos and tests."""

    dimension: int = 128
    name: str = "mock"
    model: str = "hash-ngram-v1"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [normalize_vector(_hashed_bow_vector(expand_semantic_tokens(text), self.dimension)) for text in texts]


SEMANTIC_EXPANSIONS = {
    "手续": ["审批", "报备", "许可"],
    "报备": ["审批", "许可", "手续"],
    "审批": ["报备", "许可", "手续"],
    "许可": ["审批", "报备", "手续"],
    "能飞": ["适飞", "飞行", "无人机"],
    "飞行": ["无人机", "适飞"],
    "低空": ["空域", "飞行"],
    "限制": ["管制", "禁飞"],
    "禁止": ["禁飞", "管制"],
    "管制": ["限制", "禁飞", "空域"],
    "大风": ["风速", "高风"],
    "阵风": ["风速", "高风"],
    "降雨": ["降水", "雨"],
}


def expand_semantic_tokens(text: str) -> list[str]:
    tokens = tokenize_text(text)
    expanded = list(tokens)
    for token in tokens:
        expanded.extend(SEMANTIC_EXPANSIONS.get(token, []))
    return expanded


def normalize_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        return vector
    return [round(value / norm, 12) for value in vector]


def cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float:
    if not vector_a or not vector_b or len(vector_a) != len(vector_b):
        return 0.0
    return sum(left * right for left, right in zip(vector_a, vector_b))


def provider_metadata(provider: EmbeddingProvider) -> dict[str, object]:
    return {
        "provider": provider.name,
        "model": provider.model,
        "dimension": provider.dimension,
    }


def _hashed_bow_vector(tokens: list[str], dimension: int) -> list[float]:
    vector = [0.0] * dimension
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimension
        sign = 1 if digest[4] % 2 == 0 else -1
        vector[index] += float(sign)
    return vector
