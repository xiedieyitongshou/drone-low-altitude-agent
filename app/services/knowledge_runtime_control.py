"""Immediate retrieval restrictions, independent of immutable index versions.

This sidecar is shared with the local index volume. Index publication never
resumes maintenance or removes a restriction created after a build started.
"""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.services.knowledge_index_versions import atomic_json, default_index_root, filesystem_path, index_lock


MAINTENANCE_MESSAGE = "知识检索已暂停，管理员正在维护知识库，请稍后重试。"
WITHDRAWN_MESSAGE = "相关知识已撤回或权限已调整，暂时无法提供可靠依据。"


def read_control(root: Path | None = None) -> dict:
    path = filesystem_path((root or default_index_root()) / "retrieval-control.json")
    if not path.exists():
        return {"paused": False, "message": MAINTENANCE_MESSAGE, "documents": {}, "revision": "initial"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data["paused"], bool) or not isinstance(data["documents"], dict):
            raise ValueError("Invalid retrieval control")
        for rule in data["documents"].values():
            if not isinstance(rule["blocked"], bool) or not isinstance(rule["restrictions"], list):
                raise ValueError("Invalid document restriction")
        return data
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("知识检索控制状态异常，已停止使用知识，请联系管理员。") from exc


def _save_control(root: Path, control: dict, actor: str | None) -> None:
    control.update(revision=uuid4().hex, updated_at=datetime.now(timezone.utc).isoformat(), updated_by=actor)
    atomic_json(root / "retrieval-control.json", control)


def set_retrieval_maintenance(*, paused: bool, message: str | None = None, actor: str | None = None, root: Path | None = None) -> dict:
    root = root or default_index_root()
    with index_lock(root, "control"):
        control = read_control(root)
        control.update(paused=paused, message=message or MAINTENANCE_MESSAGE)
        _save_control(root, control, actor)
    return control


def restrict_document(document, *, previous_access: dict | None = None, allow_release: bool = False, actor: str | None = None, root: Path | None = None) -> None:
    """Apply restrictions before committing an admin mutation (fail closed).

    Re-enabling or widening access only takes effect after a valid publication.
    In the meantime all access restrictions accumulated since publication apply.
    """
    root = root or default_index_root()
    with index_lock(root, "control"):
        control = read_control(root)
        old = control["documents"].get(document.id, {})
        restrictions = list(old.get("restrictions", []))
        access = {"visibility": document.visibility, "tenant_id": document.tenant_id, "user_id": document.user_id}
        negative_status = not document.is_active or document.review_status != "approved"
        blocked = bool(old.get("blocked")) or negative_status
        access_changed = previous_access is not None and previous_access != access
        if not blocked and not access_changed:
            # A normal content edit does not invalidate the published version.
            return
        if access not in restrictions:
            restrictions.append(access)
        from app.services.admin_knowledge_indexing import _document_to_advice_item

        control["documents"][document.id] = {
            "revision": uuid4().hex,
            "blocked": blocked,
            "restrictions": restrictions,
            "allowed_versions": old.get("allowed_versions"),
            "release_requested": not negative_status and (allow_release or old.get("release_requested", False)),
            "desired_sha256": _item_fingerprint(_document_to_advice_item(document)),
        }
        _save_control(root, control, actor)


def _item_fingerprint(item) -> str:
    content = json.dumps(item.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def release_published_restrictions(*, captured: dict, published_items: list, version: str, root: Path) -> None:
    with index_lock(root, "control"):
        control = read_control(root)
        for item in published_items:
            document_id = item.id
            old = captured.get("documents", {}).get(document_id)
            current = control["documents"].get(document_id)
            if old and current and old["revision"] == current["revision"]:
                if current["blocked"] and not current.get("release_requested"):
                    continue
                if current.get("desired_sha256") and current["desired_sha256"] != _item_fingerprint(item):
                    continue
                versions = [] if current["blocked"] or current["restrictions"] else list(current.get("allowed_versions") or [])
                control["documents"][document_id] = {
                    "revision": uuid4().hex, "blocked": False, "restrictions": [],
                    "allowed_versions": list(dict.fromkeys([*versions, version])),
                }
        _save_control(root, control, control.get("updated_by"))


def document_allowed(document_id: str, access_context, control: dict, index_version: str | None = None) -> bool:
    if control["paused"]:
        return False
    rule = control["documents"].get(document_id)
    if not rule:
        return True
    if rule["blocked"]:
        return False
    if rule.get("allowed_versions") is not None and index_version not in rule["allowed_versions"]:
        return False
    from app.services.vector_knowledge_store import is_document_visible

    return all(is_document_visible(restriction, access_context) for restriction in rule["restrictions"])


def filter_runtime_results(items: list, access_context=None, *, root: Path | None = None) -> list:
    control = read_control(root)
    return [item for item in items if document_allowed(item.id, access_context, control, _item_version(item))]


def _item_version(item) -> str | None:
    return getattr(item, "metadata", {}).get("index_version") or getattr(item, "index_version", None)


def _dict_version(item: dict) -> str | None:
    return (item.get("metadata") or {}).get("index_version") or item.get("index_version")


def store_retrieval_paused(store) -> bool:
    snapshot = getattr(store, "_snapshot", None)
    root = snapshot.root if snapshot else default_index_root() if store._default_location else store.index_dir
    return read_control(root)["paused"]


def finalize_retrieval(response, access_context=None, *, root: Path | None = None):
    """Recheck after retrieval/LLM relevance review, immediately before return."""
    control = read_control(root)
    if control["paused"]:
        return response.model_copy(update={
            "snippets": [], "advice": [], "retrieval_status": "maintenance",
            "retrieval_message": control.get("message") or MAINTENANCE_MESSAGE,
            "retrieval_metadata": {**response.retrieval_metadata, "reason_code": "maintenance"},
        })
    snippets = [item for item in response.snippets if document_allowed(item.id, access_context, control, _item_version(item))]
    advice = [item for item in response.advice if document_allowed(item.id, access_context, control, _item_version(item))]
    if len(snippets) != len(response.snippets) or len(advice) != len(response.advice):
        return response.model_copy(update={
            "snippets": snippets, "advice": advice,
            "retrieval_status": response.retrieval_status if snippets or advice else "fallback",
            "retrieval_message": WITHDRAWN_MESSAGE,
            "retrieval_metadata": {**response.retrieval_metadata, "runtime_restricted": True},
        })
    return response


def sanitize_composed_knowledge(response, access_context=None) -> bool:
    """Discard an explanation if any knowledge used to generate it was revoked."""
    control = read_control()
    details = response.details
    changed = False
    for key in ("advice", "knowledge_snippets"):
        items = details.get(key, [])
        allowed = [item for item in items if document_allowed(str(item.get("id", "")), access_context, control, _dict_version(item))]
        if len(allowed) != len(items):
            details[key] = allowed
            changed = True
    if control["paused"]:
        details.update(knowledge_retrieval_status="maintenance", knowledge_retrieval_message=control.get("message") or MAINTENANCE_MESSAGE)
    if changed:
        from app.services.risk_output_templates import render_business_response_template

        response.explanation = render_business_response_template(response)
        response.explanation_source = "template"
        response.llm_used = False
        details.update(knowledge_retrieval_message=WITHDRAWN_MESSAGE if not control["paused"] else control.get("message") or MAINTENANCE_MESSAGE)
    return changed


def finalize_orchestrator_knowledge(response) -> None:
    from app.schemas.advice import KnowledgeAccessContext, KnowledgeRetrievalResponse

    access = KnowledgeAccessContext(user_id=response.user_id, tenant_id="public", role="user")
    tools = (response.result or {}).get("tool_results", {})
    if isinstance(tools, dict):
        result = tools.get("query_knowledge_snippets", {})
        data = result.get("data") if isinstance(result, dict) else None
        if isinstance(data, dict) and "context" in data:
            guarded = finalize_retrieval(KnowledgeRetrievalResponse.model_validate(data), access)
            result["data"] = guarded.model_dump(mode="json")
            if guarded.retrieval_status == "maintenance" or guarded.retrieval_metadata.get("runtime_restricted"):
                response.message = guarded.retrieval_message
    if response.composed is not None:
        sanitize_composed_knowledge(response.composed, access)
