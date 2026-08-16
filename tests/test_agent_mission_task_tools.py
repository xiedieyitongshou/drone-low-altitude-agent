from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent import ToolExecutionContext, default_tool_registry
from app.db.base import Base
from app.db.models import MissionTask, User
from app.services.auth_service import hash_password
from app.services.nl_parser import NaturalLanguageParseError, parse_natural_language_request


def build_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = TestingSessionLocal()
    session.add_all(
        [
            User(
                id="user-a",
                username="user_a",
                password_hash=hash_password("demo123456"),
                role="user",
                is_active=True,
            ),
            User(
                id="user-b",
                username="user_b",
                password_hash=hash_password("demo123456"),
                role="user",
                is_active=True,
            ),
        ]
    )
    session.commit()
    return session


def test_rule_parser_detects_mission_task_intents_with_context():
    create_result = parse_natural_language_request("帮我创建一个深圳湾明天下午巡检任务")
    assert create_result.intent == "create_task"
    assert create_result.target_endpoint == "/tasks"
    assert create_result.parsed["location"] == "深圳湾"
    assert create_result.parsed["task_type"] == "inspection"
    assert create_result.parsed["start_time"] == "13:00"
    assert create_result.parsed["end_time"] == "18:00"

    context = {"current_task_id": "task-12345678", "current_task_title": "深圳湾巡检"}
    assert parse_natural_language_request("评估一下这个任务", context=context).intent == "evaluate_task"
    assert parse_natural_language_request("推荐窗口", context=context).intent == "recommend_task"
    assert parse_natural_language_request("执行前再检查一次", context=context).intent == "preflight_check_task"

    select_result = parse_natural_language_request("就选第一个窗口", context=context)
    assert select_result.intent == "select_task_window"
    assert select_result.parsed["task_id"] == "task-12345678"
    assert select_result.parsed["window_rank"] == 1


def test_rule_parser_requires_task_context_for_omitted_task_reference():
    try:
        parse_natural_language_request("评估一下这个任务")
    except NaturalLanguageParseError as exc:
        assert exc.intent == "evaluate_task"
        assert exc.missing_fields == ["task_id"]
    else:
        raise AssertionError("task operation without current task context should ask for task_id")


def test_create_mission_task_tool_uses_current_user_context():
    db = build_session()
    try:
        result = default_tool_registry.call(
            "create_mission_task",
            {
                "task_title": "深圳湾巡检",
                "purpose": "巡检",
                "location": "深圳湾",
                "date": "2026-08-18",
                "start_time": "13:00",
                "end_time": "18:00",
                "task_type": "inspection",
            },
            context=ToolExecutionContext(user_id="user-a", tenant_id="public", role="user", db=db),
        )

        assert result.success is True
        assert result.data["user_id"] == "user-a"
        assert result.data["status"] == "draft"
        task = db.get(MissionTask, result.data["id"])
        assert task is not None
        assert task.user_id == "user-a"
    finally:
        db.close()


def test_mission_task_tool_rejects_cross_user_operation():
    db = build_session()
    try:
        create_result = default_tool_registry.call(
            "create_mission_task",
            {
                "task_title": "深圳湾巡检",
                "location": "深圳湾",
                "date": "2026-08-18",
                "start_time": "13:00",
                "end_time": "18:00",
                "task_type": "inspection",
            },
            context=ToolExecutionContext(user_id="user-a", tenant_id="public", role="user", db=db),
        )
        result = default_tool_registry.call(
            "recommend_mission_task_windows",
            {"task_id": create_result.data["id"]},
            context=ToolExecutionContext(user_id="user-b", tenant_id="public", role="user", db=db),
        )

        assert result.success is False
        assert result.error_code == "MissionTaskPermissionError"
    finally:
        db.close()
