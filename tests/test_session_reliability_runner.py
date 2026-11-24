import subprocess
from unittest.mock import Mock

import pytest

from scripts.session_reliability_eval import Case, Suite


def test_readiness_records_transport_and_http_failures_before_accepting_success(monkeypatch):
    suite = object.__new__(Suite)
    suite.current = Case("readiness", "app_kill", 1)
    suite.request = Mock(side_effect=[
        RuntimeError("Compose exec failed (exit 126): OCI runtime error"),
        {"status": 503, "body": {"error_code": "DATABASE_UNAVAILABLE"}},
        {"status": 200, "body": {"id": "owner"}},
    ])
    monkeypatch.setattr("scripts.session_reliability_eval.time.sleep", lambda _: None)

    suite.wait_ready(auth=True)

    assert suite.request.call_count == 3
    for call in suite.request.call_args_list:
        assert call.args == ("/auth/me",)
        assert call.kwargs == {"server": "app_a", "record": False}
    failures = suite.current.actions[-1]["failed_probes"]
    assert failures[0]["stage"] == "probe_transport"
    assert "OCI runtime error" in failures[0]["error"]
    assert failures[1]["status"] == 503


def test_readiness_deadline_fails_with_the_last_transport_diagnostic(monkeypatch):
    suite = object.__new__(Suite)
    suite.current = None
    suite.request = Mock(side_effect=RuntimeError("probe container stopped"))
    monkeypatch.setattr("scripts.session_reliability_eval.time.monotonic", Mock(side_effect=[0, 1, 91]))
    monkeypatch.setattr("scripts.session_reliability_eval.time.sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="did not become ready.*probe container stopped"):
        suite.wait_ready()
    assert suite.request.call_count == 1


def test_compose_failure_keeps_exit_code_and_stdout_diagnostics(monkeypatch):
    suite = object.__new__(Suite)
    suite.command = ["docker", "compose", "-p", "session-reliability-test"]
    suite.env = {}
    monkeypatch.setattr("scripts.session_reliability_eval.subprocess.run", Mock(return_value=
        subprocess.CompletedProcess([], 126, stdout="OCI runtime exec failed", stderr="")))

    with pytest.raises(RuntimeError, match=r"Compose exec -T probe failed \(exit 126\): OCI runtime exec failed"):
        suite.docker("exec", "-T", "probe")
