import json
import pickle
from dataclasses import dataclass
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.schemas.advice import KnowledgeAdviceLibrary, KnowledgeAdviceItem, RetrievedKnowledgeSnippet


DEFAULT_KNOWLEDGE_PATH = Path("data/knowledge/advice_rules.json")
DEFAULT_INDEX_DIR = Path("data/knowledge/index")


@dataclass
class IndexedKnowledgeDocument:
    id: str
    title: str
    content: str
    source: str | None
    source_url: str | None
    metadata: dict[str, object]


class LocalVectorKnowledgeStore:
    """Lightweight local vector index based on TF-IDF for Day 30."""

    def __init__(self, *, knowledge_path: Path | None = None, index_dir: Path | None = None) -> None:
        self.knowledge_path = knowledge_path or DEFAULT_KNOWLEDGE_PATH
        self.index_dir = index_dir or DEFAULT_INDEX_DIR
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.vectorizer_path = self.index_dir / "tfidf_vectorizer.pkl"
        self.matrix_path = self.index_dir / "tfidf_matrix.pkl"
        self.metadata_path = self.index_dir / "documents.json"

    def build_index(self) -> int:
        library = self._load_library()
        documents = [self._to_document(item) for item in library.items]
        corpus = [doc.content for doc in documents]
        vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), lowercase=False)
        matrix = vectorizer.fit_transform(corpus)

        with self.vectorizer_path.open("wb") as file:
            pickle.dump(vectorizer, file)
        with self.matrix_path.open("wb") as file:
            pickle.dump(matrix, file)
        self.metadata_path.write_text(
            json.dumps([doc.__dict__ for doc in documents], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return len(documents)

    def retrieve(self, query_text: str, *, top_k: int = 5) -> list[RetrievedKnowledgeSnippet]:
        self._ensure_index()
        with self.vectorizer_path.open("rb") as file:
            vectorizer: TfidfVectorizer = pickle.load(file)
        with self.matrix_path.open("rb") as file:
            matrix = pickle.load(file)
        documents = [IndexedKnowledgeDocument(**item) for item in json.loads(self.metadata_path.read_text(encoding="utf-8-sig"))]

        query_vector = vectorizer.transform([query_text])
        scores = cosine_similarity(query_vector, matrix).flatten()
        ranked_indices = scores.argsort()[::-1][:top_k]

        results: list[RetrievedKnowledgeSnippet] = []
        for index in ranked_indices:
            score = float(scores[index])
            if score <= 0:
                continue
            doc = documents[index]
            results.append(
                RetrievedKnowledgeSnippet(
                    id=doc.id,
                    title=doc.title,
                    content=doc.content,
                    score=round(score, 6),
                    source=doc.source,
                    source_url=doc.source_url,
                    metadata=doc.metadata,
                )
            )
        return results

    def _ensure_index(self) -> None:
        if not self.vectorizer_path.exists() or not self.matrix_path.exists() or not self.metadata_path.exists():
            self.build_index()
            return
        if self.knowledge_path.exists():
            source_mtime = self.knowledge_path.stat().st_mtime
            index_mtime = self.metadata_path.stat().st_mtime
            if source_mtime > index_mtime:
                self.build_index()

    def _load_library(self) -> KnowledgeAdviceLibrary:
        payload = json.loads(self.knowledge_path.read_text(encoding="utf-8-sig"))
        return KnowledgeAdviceLibrary.model_validate(payload)

    def _to_document(self, item: KnowledgeAdviceItem) -> IndexedKnowledgeDocument:
        metadata = {
            "category": item.category.value,
            "risk_type": item.risk_type,
            "task_type": item.task_type,
            "warning_type": item.warning_type,
            "warning_level": item.warning_level,
            "decision_scope": item.decision_scope,
            "priority": item.priority.value,
            "action_type": item.action_type.value if item.action_type else None,
            "keywords": item.keywords,
        }
        content = "\n".join(
            [
                f"标题: {item.title}",
                f"建议: {item.advice_text}",
                f"任务类型: {' '.join(item.task_type)}",
                f"风险标签: {' '.join(item.risk_type)}",
                f"预警类型: {' '.join(item.warning_type)}",
                f"预警等级: {' '.join(item.warning_level)}",
                f"适用结论: {' '.join(item.decision_scope)}",
                f"关键词: {' '.join(item.keywords)}",
                f"备注: {item.notes or ''}",
            ]
        )
        return IndexedKnowledgeDocument(
            id=item.id,
            title=item.title,
            content=content,
            source=item.source,
            source_url=item.source_url,
            metadata=metadata,
        )


def build_retrieval_query(
    *,
    task_type: str,
    overall_decision: str | None,
    risk_reasons: list[str],
    warning_types: list[str],
    warning_levels: list[str],
) -> str:
    return "\n".join(
        [
            f"任务类型: {task_type}",
            f"总体结论: {overall_decision or ''}",
            f"风险原因: {' '.join(risk_reasons)}",
            f"预警类型: {' '.join(warning_types)}",
            f"预警等级: {' '.join(warning_levels)}",
        ]
    )
