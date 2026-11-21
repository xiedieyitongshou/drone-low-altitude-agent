from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app.services.run_observability import current_observation, measure_stage, observe_run


def test_nested_stage_times_are_inclusive_and_have_separate_self_time(monkeypatch):
    clock = iter([0.0, 0.1, 0.2, 0.3, 0.4])
    monkeypatch.setattr("app.services.run_observability.perf_counter", lambda: next(clock))
    with observe_run(user_id="owner", session_id=None) as observation:
        observation.started = 0.0
        with measure_stage("parser"):
            with measure_stage("llm"):
                pass
        summary = observation.timing_summary()
    assert summary["processing_ms"] == 400
    assert summary["stages"]["parser"]["duration_ms"] == 300
    assert summary["stages"]["parser"]["self_ms"] == 200
    assert summary["stages"]["llm"]["duration_ms"] == 100


def test_failed_stage_does_not_leave_context_for_the_next_request():
    with pytest.raises(ValueError), observe_run(user_id="owner", session_id=None) as observation:
        with measure_stage("parser"):
            raise ValueError("failed")
    assert current_observation() is None
    assert observation.samples[0]["ok"] is False
    with observe_run(user_id="next-owner", session_id=None) as next_observation:
        assert next_observation.samples == []
        assert next_observation.trace_id != observation.trace_id


def test_parallel_requests_do_not_share_trace_or_timing_samples():
    barrier = Barrier(2)

    def run(owner):
        with observe_run(user_id=owner, session_id="same-session") as observation:
            with measure_stage(owner):
                barrier.wait(timeout=5)
            return observation

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = list(executor.map(run, ["first", "second"]))
    assert first.trace_id != second.trace_id
    assert [item["stage"] for item in first.samples] == ["first"]
    assert [item["stage"] for item in second.samples] == ["second"]
    assert all(event.user_id == "first" for event in first.events)
    assert all(event.user_id == "second" for event in second.events)
