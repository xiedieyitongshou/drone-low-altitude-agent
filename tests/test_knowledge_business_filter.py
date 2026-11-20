from datetime import date

from app.schemas import KnowledgeBusinessContext
from app.services.vector_knowledge_store import is_document_applicable


def test_validity_dates_use_the_requested_date_inclusively():
    metadata = {"review_status": "approved", "effective_at": "2026-11-20", "expires_at": "2026-11-22"}
    for day, expected in ((19, False), (20, True), (22, True), (23, False)):
        context = KnowledgeBusinessContext(as_of=date(2026, 11, day))
        assert is_document_applicable(metadata, context) is expected
    assert is_document_applicable({**metadata, "effective_at": "invalid"}) is False


def test_warning_topic_is_allowed_but_known_absent_or_different_warnings_are_filtered():
    metadata = {"review_status": "approved", "warning_level": ["yellow"], "decision_scope": ["caution"]}
    assert is_document_applicable(metadata, KnowledgeBusinessContext()) is True
    assert is_document_applicable(metadata, KnowledgeBusinessContext(warning_levels=[])) is False
    assert is_document_applicable(metadata, KnowledgeBusinessContext(warning_levels=["orange"])) is False
    assert is_document_applicable(metadata, KnowledgeBusinessContext(warning_levels=["yellow"], overall_decision="慎飞")) is True
    assert is_document_applicable(metadata, KnowledgeBusinessContext(warning_levels=["yellow"], overall_decision="适飞")) is False


def test_approved_unexpired_public_business_metadata_is_applicable_without_context():
    metadata = {
        "review_status": "approved",
        "expires_at": None,
        "task_type": ["all"],
        "risk_type": [],
        "region": None,
        "province": None,
        "city": None,
    }

    assert is_document_applicable(metadata) is True


def test_draft_or_expired_knowledge_is_not_applicable():
    draft_metadata = {
        "review_status": "draft",
        "expires_at": None,
    }
    expired_metadata = {
        "review_status": "approved",
        "expires_at": "2026-01-01",
    }

    assert is_document_applicable(draft_metadata, today=date(2026, 7, 31)) is False
    assert is_document_applicable(expired_metadata, today=date(2026, 7, 31)) is False


def test_task_type_filter_allows_all_or_matching_task_type_only():
    context = KnowledgeBusinessContext(task_type="cruise")

    assert is_document_applicable({"review_status": "approved", "task_type": ["all"]}, context) is True
    assert is_document_applicable({"review_status": "approved", "task_type": ["cruise"]}, context) is True
    assert is_document_applicable({"review_status": "approved", "task_type": ["hover"]}, context) is False


def test_risk_tag_filter_allows_empty_or_overlapping_risk_tags_only():
    context = KnowledgeBusinessContext(risk_tags=["high_wind"])

    assert is_document_applicable({"review_status": "approved", "risk_type": []}, context) is True
    assert is_document_applicable({"review_status": "approved", "risk_type": ["high_wind"]}, context) is True
    assert is_document_applicable({"review_status": "approved", "risk_type": ["rainfall"]}, context) is False


def test_region_filter_allows_global_empty_or_matching_region_only():
    context = KnowledgeBusinessContext(region="深圳", province="广东", city="深圳")

    assert is_document_applicable({"review_status": "approved", "region": None}, context) is True
    assert is_document_applicable({"review_status": "approved", "region": "全国"}, context) is True
    assert is_document_applicable({"review_status": "approved", "region": "深圳"}, context) is True
    assert is_document_applicable({"review_status": "approved", "province": "广东"}, context) is True
    assert is_document_applicable({"review_status": "approved", "city": "广州"}, context) is False
