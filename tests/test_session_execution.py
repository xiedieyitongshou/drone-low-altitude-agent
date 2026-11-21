from contextlib import contextmanager
from unittest.mock import patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError

from app.services.session_execution import session_execution_guard, session_lock_key
from app.services.task_orchestrator import orchestrate_task_query


def test_same_session_is_rejected_but_other_users_and_sessions_are_independent(monkeypatch):
    monkeypatch.setenv("SESSION_MEMORY_BACKEND", "ttlcache")
    with session_execution_guard(user_id="owner", session_id="same") as first:
        assert first is True
        with session_execution_guard(user_id="owner", session_id="same") as duplicate:
            assert duplicate is False
        with session_execution_guard(user_id="other", session_id="same") as other_user:
            assert other_user is True
        with session_execution_guard(user_id="owner", session_id="different") as other_session:
            assert other_session is True
    with session_execution_guard(user_id="owner", session_id="same") as after:
        assert after is True


def test_session_guard_releases_after_an_exception(monkeypatch):
    monkeypatch.setenv("SESSION_MEMORY_BACKEND", "ttlcache")
    with pytest.raises(RuntimeError), session_execution_guard(user_id="owner", session_id="same"):
        raise RuntimeError("operation failed")
    with session_execution_guard(user_id="owner", session_id="same") as after:
        assert after is True


def test_scoped_key_has_unambiguous_user_and_session_boundaries():
    assert session_lock_key("a:b", "c") != session_lock_key("a", "b:c")
    assert session_lock_key("owner", "session") == session_lock_key("owner", "session")


def test_busy_request_does_not_call_the_business_workflow(monkeypatch):
    @contextmanager
    def busy(**kwargs):
        yield False

    monkeypatch.setattr("app.services.task_orchestrator.session_execution_guard", busy)
    monkeypatch.setattr("app.services.task_orchestrator._with_conversation_record", lambda **kwargs: kwargs["response"])
    monkeypatch.setattr("app.services.task_orchestrator._flush_observation", lambda *args, **kwargs: True)
    with patch("app.services.task_orchestrator._execute_task_query") as execute:
        response = orchestrate_task_query("创建任务", user_id="owner", session_id="same")
    execute.assert_not_called()
    assert response.success is False
    assert response.fallback == {"error_code": "SESSION_BUSY", "retryable": True}


@pytest.mark.parametrize("error,code", [
    (RedisConnectionError("private connection details"), "SESSION_STORAGE_UNAVAILABLE"),
    (OperationalError("private SQL", {}, RuntimeError("private connection details")), "DATABASE_UNAVAILABLE"),
])
def test_dependency_errors_are_explicit_and_do_not_expose_connection_details(api_client, monkeypatch, error, code):
    monkeypatch.setattr("main.anonymous_session_memory_store.get", lambda *args, **kwargs: (_ for _ in ()).throw(error))
    response = api_client.post("/nl/parse", json={"query": "深圳明天下午能飞吗", "session_id": "outage"})
    assert response.status_code == 503
    assert response.json()["error_code"] == code
    assert "private" not in response.text
