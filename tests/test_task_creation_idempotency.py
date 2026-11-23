"""Run against isolated SQLite, or a fresh schema in an explicit PostgreSQL test DB."""

from concurrent.futures import ThreadPoolExecutor
import os
from threading import Barrier, Event
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from sqlalchemy.schema import CreateSchema, DropSchema

from app.db.base import Base
from app.db.models import ConversationRecord, MissionTask, OperationRequest, User
from app.dependencies import get_db
from app.schemas import MissionTaskCreateRequest
from app.services.auth_service import create_access_token
from app.services.idempotency import IdempotencyError, OperationInProgressError
from app.services.mission_task_management import create_mission_task
from app.services.session_memory import TTLSessionMemoryStore
from app.services.task_orchestrator import orchestrate_task_query
from main import app


@pytest.fixture
def operation_factory(tmp_path, monkeypatch):
    url = os.getenv("IDEMPOTENCY_TEST_DATABASE_URL") or f"sqlite:///{(tmp_path / 'operations.db').as_posix()}"
    engine = create_engine(url, **({"connect_args": {"check_same_thread": False, "timeout": 20}} if url.startswith("sqlite") else {}))
    schema = None
    if engine.dialect.name == "postgresql":
        schema = f"idempotency_{uuid4().hex}"
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        bind = engine.execution_options(schema_translate_map={None: schema})
    else:
        bind = engine
    Base.metadata.create_all(bind)
    factory = sessionmaker(bind=bind, autoflush=False)
    with factory.begin() as db:
        db.add_all(User(id=name, username=name, password_hash="UNUSABLE_PASSWORD", role="user") for name in ("owner", "other"))
    monkeypatch.setenv("AGENT_RUNTIME_MODE", "loop")
    monkeypatch.setenv("NL_PARSER_MODE", "rule")
    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.setattr("app.services.profile_memory.SessionLocal", factory)
    monkeypatch.setattr("app.services.task_orchestrator.session_memory_store", TTLSessionMemoryStore())
    try:
        yield factory
    finally:
        if schema:
            with engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()


@pytest.fixture
def operation_client(operation_factory, monkeypatch):
    def database():
        with operation_factory() as db:
            yield db

    monkeypatch.setitem(app.dependency_overrides, get_db, database)
    # No application lifespan/background cleanup needs to access a real DB.
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()


def payload(**changes):
    return MissionTaskCreateRequest(title="Inspection", location="Shenzhen Bay", **changes)


def create(factory, key="operation-a", user_id="owner", request=None):
    with factory() as db:
        return create_mission_task(
            db=db, current_user=db.get(User, user_id), payload=request or payload(), idempotency_key=key,
        )


def count(factory, model):
    with factory() as db:
        return db.scalar(select(func.count()).select_from(model))


def agent(factory, key="agent-a", query="帮我创建一个深圳湾明天下午巡检任务", session_id="session-a", user_id="owner"):
    with factory() as db:
        return orchestrate_task_query(query, session_id=session_id, user_id=user_id, db=db, idempotency_key=key)


def headers(key="operation-a", user_id="owner"):
    return {"Authorization": f"Bearer {create_access_token(user_id)}", "Idempotency-Key": key}


def test_serial_retry_returns_original_snapshot_even_after_task_changes(operation_factory):
    first = create(operation_factory)
    with operation_factory.begin() as db:
        task = db.get(MissionTask, first.id)
        task.title = "Later edit"
        task.status = "cancelled"
    retried = create(operation_factory)
    assert retried.model_dump(mode="json") == first.model_dump(mode="json")
    assert count(operation_factory, MissionTask) == 1
    assert count(operation_factory, OperationRequest) == 1


def test_distinct_keys_and_users_do_not_merge_identical_content(operation_factory):
    results = [create(operation_factory), create(operation_factory, key="operation-b"), create(operation_factory, user_id="other")]
    assert len({item.id for item in results}) == 3


def test_changed_content_under_same_key_is_rejected(operation_factory):
    first = create(operation_factory)
    with pytest.raises(IdempotencyError):
        create(operation_factory, request=payload(purpose="changed"))
    assert count(operation_factory, MissionTask) == 1
    assert create(operation_factory).id == first.id


def test_request_hash_uses_validated_fields_and_stable_json_order(operation_factory):
    first = create(operation_factory, request=payload(metadata={"a": 1, "b": 2}))
    second = create(operation_factory, request=payload(metadata={"b": 2, "a": 1}))
    assert first.id == second.id


def test_parallel_retries_use_database_constraint(operation_factory):
    barrier = Barrier(4)

    def submit():
        barrier.wait(timeout=10)
        return create(operation_factory).model_dump(mode="json")

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: submit(), range(4)))
    assert all(item == results[0] for item in results)
    assert count(operation_factory, MissionTask) == 1
    assert count(operation_factory, OperationRequest) == 1


def test_failure_before_commit_rolls_back_both_task_and_receipt(operation_factory, monkeypatch):
    with monkeypatch.context() as patcher:
        def fail(_):
            raise RuntimeError("injected after task flush")
        patcher.setattr("app.services.mission_task_management.to_mission_task_response", fail)
        with pytest.raises(RuntimeError):
            create(operation_factory)
    assert count(operation_factory, MissionTask) == 0
    assert count(operation_factory, OperationRequest) == 0
    create(operation_factory)
    assert count(operation_factory, MissionTask) == 1


def test_http_post_commit_response_loss_and_retry(operation_client, operation_factory, monkeypatch):
    original = create_mission_task
    committed = []

    def lose_response(**kwargs):
        committed.append(original(**kwargs).model_dump(mode="json"))
        raise ConnectionResetError("injected response loss after commit")

    with monkeypatch.context() as patcher:
        patcher.setattr("main.create_mission_task", lose_response)
        with pytest.raises(ConnectionResetError):
            operation_client.post("/tasks", headers=headers(), json=payload().model_dump(mode="json"))
    retry = operation_client.post("/tasks", headers=headers(), json=payload().model_dump(mode="json"))
    assert retry.status_code == 201
    assert retry.json() == committed[0]
    assert count(operation_factory, MissionTask) == 1


def test_http_conflict_and_header_validation(operation_client, operation_factory):
    assert operation_client.post("/tasks", headers=headers(), json={"title": "one"}).status_code == 201
    conflict = operation_client.post("/tasks", headers=headers(), json={"title": "two"})
    assert conflict.status_code == 409
    assert conflict.json()["error_code"] == "IDEMPOTENCY_KEY_REUSED"
    assert operation_client.post("/tasks", headers=headers("invalid key"), json={"title": "one"}).status_code == 422
    assert count(operation_factory, MissionTask) == 1


def test_commit_acknowledgement_loss_is_recoverable(operation_factory, monkeypatch):
    with operation_factory() as db:
        owner = db.get(User, "owner")
        commit = db.commit

        def disconnect_after_commit():
            commit()
            db.close()
            raise OperationalError("injected disconnect after COMMIT", {}, ConnectionResetError(), connection_invalidated=True)

        monkeypatch.setattr(db, "commit", disconnect_after_commit)
        with pytest.raises(OperationalError):
            create_mission_task(db=db, current_user=owner, payload=payload(), idempotency_key="operation-a")
    assert count(operation_factory, MissionTask) == 1
    assert count(operation_factory, OperationRequest) == 1
    create(operation_factory)
    assert count(operation_factory, MissionTask) == 1


def test_legacy_clients_without_keys_keep_explicit_new_creation_behavior(operation_client, operation_factory):
    authorization = {"Authorization": headers()["Authorization"]}
    responses = [operation_client.post("/tasks", headers=authorization, json={"title": "same"}) for _ in range(2)]
    assert all(response.status_code == 201 for response in responses)
    assert responses[0].json()["id"] != responses[1].json()["id"]
    assert count(operation_factory, MissionTask) == 2


def test_agent_http_replay_uses_token_identity_and_rejects_changed_query(operation_client, operation_factory):
    request = {"query": "帮我创建一个深圳湾明天下午巡检任务", "session_id": "same", "user_id": "spoofed"}
    first = operation_client.post("/agent/query", headers=headers(), json=request)
    assert first.status_code == 200 and first.json()["success"]
    retry = operation_client.post("/agent/query", headers=headers(), json={**request, "user_id": "another-spoof"})
    assert retry.json() == first.json()
    assert retry.json()["user_id"] == "owner"
    conflict = operation_client.post("/agent/query", headers=headers(), json={**request, "query": "different query"})
    assert conflict.status_code == 409
    assert conflict.json()["error_code"] == "IDEMPOTENCY_KEY_REUSED"
    assert count(operation_factory, MissionTask) == 1


@pytest.mark.parametrize("mode", ["loop", "legacy"])
def test_agent_replay_skips_parser_and_all_business_side_effects(operation_factory, monkeypatch, mode):
    monkeypatch.setenv("AGENT_RUNTIME_MODE", mode)
    first = agent(operation_factory)
    assert first.success and first.intent == "create_task"
    with monkeypatch.context() as patcher:
        def unexpected(*args, **kwargs):
            raise AssertionError("replay must not run the parser")
        patcher.setattr("app.services.task_orchestrator._parse_task_query", unexpected)
        retried = agent(operation_factory)
    assert retried.model_dump(mode="json") == first.model_dump(mode="json")
    assert count(operation_factory, MissionTask) == 1
    assert count(operation_factory, ConversationRecord) == 1


def test_agent_recovers_creation_after_interruption_before_final_response(operation_factory, monkeypatch):
    original = create_mission_task

    def interrupt(**kwargs):
        original(**kwargs)
        raise SystemExit("injected worker interruption after task commit")

    with monkeypatch.context() as patcher:
        patcher.setattr("app.agent.tools.create_mission_task", interrupt)
        with pytest.raises(SystemExit):
            agent(operation_factory)
    assert count(operation_factory, MissionTask) == 1
    with monkeypatch.context() as patcher:
        def unexpected(*args, **kwargs):
            raise AssertionError("recovery must use the frozen task, not reinterpret relative dates")
        patcher.setattr("app.services.task_orchestrator._parse_task_query", unexpected)
        recovered = agent(operation_factory)
    assert recovered.success and recovered.agent_runtime["idempotency_recovered"]
    assert count(operation_factory, MissionTask) == 1
    assert agent(operation_factory).model_dump(mode="json") == recovered.model_dump(mode="json")


def test_agent_rejects_changed_envelope_and_new_key_creates_new_task(operation_factory):
    first = agent(operation_factory)
    for change in ({"query": "帮我创建一个北京明天下午巡检任务"}, {"session_id": "another-session"}):
        with pytest.raises(IdempotencyError):
            agent(operation_factory, **change)
    assert count(operation_factory, MissionTask) == 1
    assert agent(operation_factory, key="agent-b").success
    assert count(operation_factory, MissionTask) == 2
    assert agent(operation_factory).conversation_id == first.conversation_id


def test_overlapping_agent_retry_reports_busy_then_replays(operation_factory, monkeypatch):
    entered, release = Event(), Event()
    from app.services.mission_task_management import _insert_mission_task

    def blocked(**kwargs):
        entered.set()
        assert release.wait(timeout=15)
        return _insert_mission_task(**kwargs)

    with monkeypatch.context() as patcher, ThreadPoolExecutor(max_workers=1) as pool:
        patcher.setattr("app.services.mission_task_management._insert_mission_task", blocked)
        first = pool.submit(agent, operation_factory)
        try:
            assert entered.wait(timeout=15)
            with pytest.raises(OperationInProgressError):
                agent(operation_factory)
        finally:
            release.set()
        response = first.result(timeout=15)
    assert response.success
    assert agent(operation_factory).model_dump(mode="json") == response.model_dump(mode="json")
    assert count(operation_factory, MissionTask) == 1
