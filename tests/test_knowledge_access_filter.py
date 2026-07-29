from app.schemas import KnowledgeAccessContext
from app.services.vector_knowledge_store import is_document_visible


def test_public_knowledge_is_visible_without_access_context():
    metadata = {
        "visibility": "public",
        "tenant_id": "tenant-a",
        "user_id": "user-a",
    }

    assert is_document_visible(metadata) is True


def test_tenant_knowledge_requires_matching_tenant_id():
    metadata = {
        "visibility": "tenant",
        "tenant_id": "tenant-a",
        "user_id": None,
    }

    assert is_document_visible(metadata, KnowledgeAccessContext(user_id="user-a", tenant_id="tenant-a")) is True
    assert is_document_visible(metadata, KnowledgeAccessContext(user_id="user-b", tenant_id="tenant-b")) is False
    assert is_document_visible(metadata) is False


def test_private_knowledge_requires_matching_user_id():
    metadata = {
        "visibility": "private",
        "tenant_id": "tenant-a",
        "user_id": "user-a",
    }

    assert is_document_visible(metadata, KnowledgeAccessContext(user_id="user-a", tenant_id="tenant-a")) is True
    assert is_document_visible(metadata, KnowledgeAccessContext(user_id="user-b", tenant_id="tenant-a")) is False
    assert is_document_visible(metadata) is False


def test_unknown_visibility_is_not_visible():
    metadata = {
        "visibility": "internal-only",
        "tenant_id": "tenant-a",
        "user_id": "user-a",
    }

    assert is_document_visible(metadata, KnowledgeAccessContext(user_id="user-a", tenant_id="tenant-a")) is False
