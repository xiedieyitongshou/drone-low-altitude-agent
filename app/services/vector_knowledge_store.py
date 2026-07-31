import json
import pickle
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.schemas.advice import (
    KnowledgeAccessContext,
    KnowledgeAdviceLibrary,
    KnowledgeAdviceItem,
    KnowledgeBusinessContext,
    KnowledgeReviewStatus,
    KnowledgeVisibility,
    RetrievedKnowledgeSnippet,
)


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

    def retrieve(
        self,
        query_text: str,
        *,
        top_k: int = 5,
        access_context: KnowledgeAccessContext | None = None,
        business_context: KnowledgeBusinessContext | None = None,
    ) -> list[RetrievedKnowledgeSnippet]:
        self._ensure_index()
        with self.vectorizer_path.open("rb") as file:
            vectorizer: TfidfVectorizer = pickle.load(file)
        with self.matrix_path.open("rb") as file:
            matrix = pickle.load(file)
        documents = [IndexedKnowledgeDocument(**item) for item in json.loads(self.metadata_path.read_text(encoding="utf-8-sig"))]

        query_vector = vectorizer.transform([query_text])
        scores = cosine_similarity(query_vector, matrix).flatten()
        ranked_indices = scores.argsort()[::-1]

        results: list[RetrievedKnowledgeSnippet] = []
        for index in ranked_indices:
            if len(results) >= top_k:
                break
            score = float(scores[index])
            if score <= 0:
                continue
            doc = documents[index]
            if not is_document_visible(doc.metadata, access_context):
                continue
            if not is_document_applicable(doc.metadata, business_context):
                continue
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
            "knowledge_type": item.knowledge_type.value,
            "risk_type": item.risk_type,
            "task_type": item.task_type,
            "warning_type": item.warning_type,
            "warning_level": item.warning_level,
            "decision_scope": item.decision_scope,
            "region": item.region,
            "province": item.province,
            "city": item.city,
            "visibility": item.visibility.value,
            "tenant_id": item.tenant_id,
            "user_id": item.user_id,
            "version": item.version,
            "effective_at": item.effective_at,
            "expires_at": item.expires_at,
            "review_status": item.review_status.value,
            "priority": item.priority.value,
            "action_type": item.action_type.value if item.action_type else None,
            "keywords": item.keywords,
        }
        content = "\n".join(
            [
                f"标题: {item.title}",
                f"建议: {item.advice_text}",
                f"知识类型: {item.knowledge_type}",
                f"任务类型: {' '.join(item.task_type)}",
                f"风险标签: {' '.join(item.risk_type)}",
                f"预警类型: {' '.join(item.warning_type)}",
                f"预警等级: {' '.join(item.warning_level)}",
                f"适用结论: {' '.join(item.decision_scope)}",
                f"适用地区: {' '.join(value for value in [item.province, item.city, item.region] if value)}",
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


def is_document_visible(
    metadata: dict[str, object],
    access_context: KnowledgeAccessContext | None = None,
) -> bool:
    visibility = str(metadata.get("visibility") or KnowledgeVisibility.PUBLIC.value)
    if visibility == KnowledgeVisibility.PUBLIC.value:
        return True

    if access_context is None:
        return False

    if visibility == KnowledgeVisibility.TENANT.value:
        document_tenant_id = metadata.get("tenant_id")
        return bool(access_context.tenant_id) and document_tenant_id == access_context.tenant_id

    if visibility == KnowledgeVisibility.PRIVATE.value:
        document_user_id = metadata.get("user_id")
        return bool(access_context.user_id) and document_user_id == access_context.user_id

    return False


def is_document_applicable(
    metadata: dict[str, object],
    business_context: KnowledgeBusinessContext | None = None,
    *,
    today: date | None = None,
) -> bool:
    if metadata.get("review_status") != KnowledgeReviewStatus.APPROVED.value:
        return False

    if _is_expired(metadata.get("expires_at"), today=today):
        return False

    if business_context is None:
        return True

    if not _matches_task_type(metadata.get("task_type"), business_context.task_type):
        return False

    if not _matches_risk_tags(metadata.get("risk_type"), business_context.risk_tags):
        return False

    if not _matches_region(
        region=metadata.get("region"),
        province=metadata.get("province"),
        city=metadata.get("city"),
        business_context=business_context,
    ):
        return False

    return True


def _is_expired(value: object, *, today: date | None = None) -> bool:
    if value in (None, ""):
        return False
    if not isinstance(value, str):
        return True
    try:
        expires_at = date.fromisoformat(value)
    except ValueError:
        return True
    return expires_at < (today or date.today())


def _matches_task_type(value: object, task_type: str | None) -> bool:
    task_types = _to_string_list(value)
    if not task_types or "all" in task_types or not task_type:
        return True
    return task_type in task_types


def _matches_risk_tags(value: object, risk_tags: list[str]) -> bool:
    document_risk_tags = set(_to_string_list(value))
    if not document_risk_tags or not risk_tags:
        return True
    return bool(document_risk_tags & set(risk_tags))


def _matches_region(
    *,
    region: object,
    province: object,
    city: object,
    business_context: KnowledgeBusinessContext,
) -> bool:
    document_region = _normalize_text(region)
    document_province = _normalize_text(province)
    document_city = _normalize_text(city)
    if not any([document_region, document_province, document_city]):
        return True
    if "\u5168\u56fd" in {document_region, document_province, document_city}:
        return True

    context_region = _normalize_text(business_context.region)
    context_province = _normalize_text(business_context.province)
    context_city = _normalize_text(business_context.city)
    if not any([context_region, context_province, context_city]):
        return True

    if document_city:
        return document_city in {context_city, context_region}
    if document_region:
        return document_region in {context_region, context_city, context_province}
    if document_province:
        return document_province in {context_province, context_region}

    return True


def _normalize_text(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value).strip() or None


def _to_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def build_retrieval_query(
    *,
    task_type: str,
    overall_decision: str | None,
    risk_reasons: list[str],
    warning_types: list[str],
    warning_levels: list[str],
    region: str | None = None,
    province: str | None = None,
    city: str | None = None,
) -> str:
    return "\n".join(
        [
            f"任务类型: {task_type}",
            f"总体结论: {overall_decision or ''}",
            f"风险原因: {' '.join(risk_reasons)}",
            f"预警类型: {' '.join(warning_types)}",
            f"预警等级: {' '.join(warning_levels)}",
            f"任务地区: {' '.join(value for value in [province, city, region] if value)}",
        ]
    )
