import re
from dataclasses import dataclass

from app.schemas.advice import KnowledgeAdviceItem, KnowledgeAdviceLibrary
from app.services.vector_knowledge_store import IndexedKnowledgeDocument, build_indexed_documents


@dataclass
class IndexedKnowledgeChunk:
    id: str
    knowledge_id: str
    chunk_type: str
    chunk_index: int
    title: str
    content: str
    source: str | None
    source_url: str | None
    metadata: dict[str, object]


def build_indexed_chunks(library: KnowledgeAdviceLibrary) -> list[IndexedKnowledgeChunk]:
    documents = {document.id: document for document in build_indexed_documents(library)}
    chunks: list[IndexedKnowledgeChunk] = []
    for item in library.items:
        document = documents[item.id]
        chunk_texts = _chunk_item(item)
        for index, chunk_text in enumerate(chunk_texts):
            chunk_type = _chunk_type_for_knowledge(item.knowledge_type.value)
            chunk_id = f"{item.id}::chunk-{index + 1}"
            chunks.append(_to_chunk(item, document, chunk_id, chunk_type, index, chunk_text))
    return chunks


def _to_chunk(
    item: KnowledgeAdviceItem,
    document: IndexedKnowledgeDocument,
    chunk_id: str,
    chunk_type: str,
    chunk_index: int,
    chunk_text: str,
) -> IndexedKnowledgeChunk:
    return IndexedKnowledgeChunk(
        id=chunk_id,
        knowledge_id=item.id,
        chunk_type=chunk_type,
        chunk_index=chunk_index,
        title=item.title,
        content=_chunk_content(item, chunk_text),
        source=item.source,
        source_url=item.source_url,
        metadata={
            **document.metadata,
            "knowledge_id": item.id,
            "chunk_id": chunk_id,
            "chunk_type": chunk_type,
            "chunk_index": chunk_index,
            "chunk_strategy": item.knowledge_type.value,
        },
    )


def _chunk_item(item: KnowledgeAdviceItem) -> list[str]:
    text = "\n".join(value for value in [item.advice_text, item.notes or ""] if value).strip()
    if not text:
        return [item.title]

    knowledge_type = item.knowledge_type.value
    if knowledge_type == "policy_hint":
        return _split_policy_text(text)
    if knowledge_type == "sop":
        return _split_sop_text(text)
    if knowledge_type == "faq":
        return _split_faq_text(text)
    if knowledge_type == "risk_advice":
        return _split_risk_advice_text(text)
    return [text]


def _chunk_content(item: KnowledgeAdviceItem, chunk_text: str) -> str:
    return "\n".join(
        [
            f"标题: {item.title}",
            f"片段: {chunk_text}",
            f"知识类型: {item.knowledge_type.value}",
            f"任务类型: {' '.join(item.task_type)}",
            f"风险标签: {' '.join(item.risk_type)}",
            f"适用地区: {' '.join(value for value in [item.province, item.city, item.region] if value)}",
            f"关键词: {' '.join(item.keywords)}",
        ]
    )


def _chunk_type_for_knowledge(knowledge_type: str) -> str:
    return {
        "policy_hint": "policy_clause",
        "sop": "sop_step",
        "faq": "qa_pair",
        "risk_advice": "risk_block",
    }.get(knowledge_type, "text_block")


def _split_policy_text(text: str) -> list[str]:
    return _non_empty_parts(
        re.split(r"(?:\n{2,}|第[一二三四五六七八九十\d]+条[:：、.]?|Article\s*\d+[:：.]?)", text, flags=re.IGNORECASE)
    ) or [text]


def _split_sop_text(text: str) -> list[str]:
    parts = _non_empty_parts(re.split(r"(?:\n+|步骤\s*\d+[:：、.]?|Step\s*\d+[:：.]?|\d+[.、])", text))
    return parts or [text]


def _split_faq_text(text: str) -> list[str]:
    qa_pairs = re.findall(r"(?:Q[:：].*?A[:：].*?)(?=(?:\nQ[:：])|\Z)", text, flags=re.DOTALL | re.IGNORECASE)
    return _non_empty_parts(qa_pairs) or _non_empty_parts(text.split("\n\n")) or [text]


def _split_risk_advice_text(text: str) -> list[str]:
    if len(text) <= 180:
        return [text]
    return _non_empty_parts(re.split(r"(?:\n+|[；;])", text)) or [text]


def _non_empty_parts(parts: list[str]) -> list[str]:
    return [part.strip() for part in parts if part and part.strip()]
