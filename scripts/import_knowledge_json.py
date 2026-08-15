import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_environment
from app.db.base import Base
from app.db.models import KnowledgeDocument
from app.db.session import SessionLocal, engine
from app.schemas.advice import KnowledgeAdviceLibrary


DEFAULT_KNOWLEDGE_PATH = Path("data/knowledge/advice_rules.json")


@dataclass(frozen=True)
class ImportKnowledgeResult:
    created: int
    updated: int
    total: int


def import_knowledge_json(path: Path = DEFAULT_KNOWLEDGE_PATH) -> ImportKnowledgeResult:
    payload = _load_and_validate_payload(path)
    created = 0
    updated = 0

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        for item in payload.items:
            existing = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id == item.id))
            values = _map_item_to_document_values(item.model_dump(mode="json"), library_version=payload.version)
            if existing is None:
                db.add(KnowledgeDocument(**values))
                created += 1
            else:
                for field_name, value in values.items():
                    if field_name == "id":
                        continue
                    setattr(existing, field_name, value)
                updated += 1
        db.commit()

    return ImportKnowledgeResult(created=created, updated=updated, total=len(payload.items))


def _load_and_validate_payload(path: Path) -> KnowledgeAdviceLibrary:
    resolved_path = path.resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"knowledge json not found: {resolved_path}")
    raw_payload = json.loads(resolved_path.read_text(encoding="utf-8-sig"))
    return KnowledgeAdviceLibrary.model_validate(raw_payload)


def _map_item_to_document_values(item: dict[str, Any], *, library_version: str) -> dict[str, Any]:
    metadata = {
        "priority": item.get("priority"),
        "action_type": item.get("action_type"),
        "notes": item.get("notes"),
        "library_version": library_version,
        "source_format": "json_import",
    }
    return {
        "id": item["id"],
        "title": item["title"],
        "content": item["advice_text"],
        "knowledge_type": item.get("knowledge_type") or "risk_advice",
        "category": item.get("category"),
        "region": item.get("region"),
        "province": item.get("province"),
        "city": item.get("city"),
        "task_types_json": _as_list(item.get("task_type")),
        "risk_tags_json": _as_list(item.get("risk_type")),
        "warning_types_json": _as_list(item.get("warning_type")),
        "warning_levels_json": _as_list(item.get("warning_level")),
        "decision_scopes_json": _as_list(item.get("decision_scope")),
        "keywords_json": _as_list(item.get("keywords")),
        "visibility": item.get("visibility") or "public",
        "tenant_id": item.get("tenant_id") or "public",
        "user_id": item.get("user_id"),
        "version": item.get("version") or library_version,
        "review_status": "approved",
        "is_active": True,
        "index_dirty": True,
        "effective_at": item.get("effective_at"),
        "expires_at": item.get("expires_at"),
        "source": item.get("source"),
        "source_url": item.get("source_url"),
        "metadata_json": {key: value for key, value in metadata.items() if value not in (None, "", [])},
    }


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import data/knowledge/advice_rules.json into knowledge_documents.")
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_KNOWLEDGE_PATH,
        help="Path to advice_rules.json. Defaults to data/knowledge/advice_rules.json.",
    )
    return parser.parse_args()


def main() -> None:
    load_environment()
    args = parse_args()
    result = import_knowledge_json(args.path)
    print(
        "Imported knowledge JSON into knowledge_documents: "
        f"created={result.created}, updated={result.updated}, total={result.total}, index_dirty=true"
    )


if __name__ == "__main__":
    main()
