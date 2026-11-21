"""Run real-process Session fault drills in a disposable, network-isolated Compose project.

Only the HTTP weather provider is a fixture. Application processes, HTTP requests,
PostgreSQL, Redis, process restarts, TTL expiry and database writes are real.
"""

import argparse
import json
import os
import re
import subprocess
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker/session_reliability.compose.yml"
SCENARIOS = [
    "multiturn", "app_restart", "app_kill", "cross_instance", "postgres_restart",
    "postgres_outage", "postgres_expiry", "redis_expiry", "redis_outage", "redis_restart",
    "isolation", "session_save_failure", "concurrent_update", "crash_before_session_write",
]


def sql_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def redact(value):
    if isinstance(value, dict):
        return {key: "[REDACTED]" if key.lower() in {"access_token", "password", "token", "authorization"}
                else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


@dataclass
class Case:
    id: str
    scenario: str
    iteration: int
    actions: list = field(default_factory=list)
    checks: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def check(self, name, actual, expected=True):
        self.checks.append({"name": name, "actual": actual, "expected": expected, "passed": actual == expected})

    def result(self):
        return {**self.__dict__, "passed": bool(self.checks) and all(item["passed"] for item in self.checks)}


class Suite:
    def __init__(self, args):
        self.args = args
        self.project = args.project or f"session-reliability-{datetime.now():%Y%m%d%H%M%S}-{uuid4().hex[:5]}"
        if not re.fullmatch(r"session-reliability-[a-z0-9-]+", self.project):
            raise ValueError("Project name must start with session-reliability- and contain lowercase letters/digits/hyphens")
        self.env = {**os.environ, "SESSION_RELIABILITY_IMAGE": args.image}
        self.command = ["docker", "compose", "-f", str(COMPOSE), "-p", self.project]
        self.output = (args.output or ROOT / "data/eval-reports/session-reliability" / self.project).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.current = None
        self.results = []
        self.tokens = {}
        self.users = {}
        self.actions = []
        image = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", args.image], capture_output=True, text=True)
        self.image_id = image.stdout.strip()
        self.source_hashes = {}
        for name in ("main.py", "app/db/session.py", "app/services/task_orchestrator.py", "app/services/session_execution.py",
                     "scripts/session_reliability_eval.py", "scripts/session_reliability_probe.py", "scripts/session_reliability_fixture.py",
                     "docker/session_reliability.compose.yml"):
            path = ROOT / name
            if path.exists():
                import hashlib

                self.source_hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()

    def docker(self, *args, input=None, timeout=120, check=True):
        result = subprocess.run(
            [*self.command, *args], input=input, capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=self.env, cwd=ROOT, timeout=timeout,
        )
        if check and result.returncode:
            raise RuntimeError(f"Compose {args[0]} failed: {result.stderr[-1500:]}")
        return result

    def sql(self, statement):
        result = self.docker("exec", "-T", "postgres", "psql", "-U", "session_test", "-d", "session_reliability",
                             "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", statement)
        return result.stdout.strip()

    def sql_json(self, query):
        return json.loads(self.sql(f"SELECT coalesce(json_agg(row_to_json(x)), '[]'::json) FROM ({query}) x"))

    def redis(self, *args):
        return self.docker("exec", "-T", "redis", "redis-cli", "--raw", *args).stdout.strip()

    def probe(self, items, parallel=False, record=True):
        result = self.docker("exec", "-T", "probe", "python", "scripts/session_reliability_probe.py",
                             input=json.dumps({"requests": items, "parallel": parallel}, ensure_ascii=False))
        responses = json.loads(result.stdout)
        if record and self.current:
            self.current.actions.append({"kind": "http", "parallel": parallel,
                                         "requests": redact(items), "responses": redact(responses)})
        return responses

    def request(self, path, *, server="app_a", owner="owner", body=None, method=None, record=True):
        item = {"url": f"http://{server}:8000{path}", "method": method or ("POST" if body is not None else "GET")}
        if owner in self.tokens:
            item["token"] = self.tokens[owner]
        if body is not None:
            item["json"] = body
        response = self.probe([item], record=record)[0]
        response["client_received_at_monotonic"] = time.monotonic()
        return response

    def wait_ready(self, server="app_a", auth=False):
        deadline = time.monotonic() + 90
        failures = []
        while time.monotonic() < deadline:
            response = self.request("/auth/me" if auth else "/health", server=server, record=False)
            if response["status"] == 200:
                if self.current:
                    self.current.actions.append({"kind": "ready", "server": server, "failed_probes": failures})
                return
            failures.append({"status": response["status"], "body": response["body"]})
            time.sleep(0.3)
        raise RuntimeError(f"{server} did not become ready")

    def account(self, owner):
        username = f"sr-{owner}-{uuid4().hex[:8]}"
        credentials = {"username": username, "password": "isolated-session-reliability-password"}
        registered = self.request("/auth/register", owner=None, body=credentials, record=False)
        if registered["status"] != 201:
            raise RuntimeError(f"Account creation failed: {registered['body']}")
        self.users[owner] = registered["body"]["id"]
        login = self.request("/auth/login", owner=None, body=credentials, record=False)
        self.tokens[owner] = login["body"]["access_token"]

    def control(self, **values):
        self.probe([{"url": "http://weather:8080/control", "method": "POST", "json": values}], record=False)

    def weather_count(self):
        result = self.probe([{"url": "http://weather:8080/control"}], record=False)[0]
        return len(result["body"]["calls"])

    def query(self, text, sid, *, owner="owner", server="app_a"):
        response = self.request("/agent/query", server=server, owner=owner, body={"query": text, "session_id": sid})
        payload = response["body"]
        trace_id = payload.get("trace_id")
        if trace_id and response["status"] == 200:
            trace = self.request(f"/agent/traces/{trace_id}", owner=owner, server=server)
            self.current.actions.append({"kind": "trace", "trace_id": trace_id, "detail": trace["body"]})
        return response

    def snapshot(self, sid, owner="owner"):
        rows = self.sql_json(f"SELECT user_id,session_id,last_context,updated_at,expires_at FROM session_records "
                             f"WHERE user_id={sql_literal(self.users[owner])} AND session_id={sql_literal(sid)}")
        self.current.actions.append({"kind": "session_snapshot", "owner": owner, "session_id": sid, "rows": rows})
        return rows[0]["last_context"] if rows else None

    def fields(self, response, **expected):
        tool = (response["body"].get("result") or {}).get("tool_results", {}).get("evaluate_flight_risk", {})
        request = (tool.get("data") or {}).get("request", {})
        self.current.check("business_success", response["status"] == 200 and response["body"].get("success") is True)
        for key, value in expected.items():
            self.current.check(f"field:{key}", request.get(key), value)
        trace = next((action["detail"] for action in reversed(self.current.actions)
                      if action["kind"] == "trace" and action["trace_id"] == response["body"].get("trace_id")), {})
        actual_inputs = [item.get("input_summary", {}) for item in trace.get("events", [])
                         if item.get("event_type") == "tool_call" and item.get("tool_name") == "evaluate_flight_risk"]
        self.current.check("actual_tool_call_recorded", bool(actual_inputs))
        if actual_inputs:
            for key, value in expected.items():
                self.current.check(f"field:trace_tool_{key}", actual_inputs[-1].get(key), value)
        return request

    def pending(self, sid):
        response = self.query("明天下午2点到3点巡检能飞吗", sid)
        self.current.check("clarification_before_fault", response["body"].get("agent_runtime", {}).get("status"), "needs_clarification")
        before = self.snapshot(sid)
        self.current.check("pending_persisted", bool(before and before.get("pending_task")))
        return before

    def continue_pending(self, sid, before, *, server="app_a", fault_started=None):
        expected = before.get("pending_task", {}).get("parsed", {}) if before else {}
        response = self.query("深圳", sid, server=server)
        request = self.fields(response, location="深圳", date=expected.get("date"), start_time="14:00", end_time="15:00", task_type="inspection")
        self.current.metrics["restoration_eligible"] = True
        self.current.metrics["restored"] = response["body"].get("success") is True and all(
            request.get(key) == value for key, value in {"location": "深圳", "date": expected.get("date"),
                                                        "start_time": "14:00", "end_time": "15:00", "task_type": "inspection"}.items())
        if fault_started is not None:
            self.current.metrics["recovery_ms"] = round((response["client_received_at_monotonic"] - fault_started) * 1000, 3)
        self.current.metrics["continuation_latency_ms"] = response["latency_ms"]
        self.snapshot(sid)

    def process_action(self, action, service):
        started = time.monotonic()
        self.docker(action, service)
        self.current.actions.append({"kind": "process", "action": action, "service": service,
                                     "elapsed_ms": round((time.monotonic() - started) * 1000, 3)})

    def case_multiturn(self, sid):
        for query, location, task_type in (
            ("深圳明天下午2点到3点巡检能飞吗", "深圳", "inspection"),
            ("地点改成广州", "广州", "inspection"),
            ("任务类型改成测绘", "广州", "survey"),
        ):
            response = self.query(query, sid)
            self.fields(response, location=location, task_type=task_type, start_time="14:00", end_time="15:00")
            stored = self.snapshot(sid)
            self.current.check("persisted_fields_match_tool", bool(stored and stored.get("location") == location and stored.get("task_type") == task_type))

    def case_app_restart(self, sid):
        before = self.pending(sid)
        started = time.monotonic()
        self.process_action("restart", "app_a")
        self.wait_ready(auth=True)
        self.continue_pending(sid, before, fault_started=started)

    def case_app_kill(self, sid):
        before = self.pending(sid)
        started = time.monotonic()
        self.docker("kill", "-s", "SIGKILL", "app_a")
        self.current.actions.append({"kind": "process", "action": "SIGKILL", "service": "app_a"})
        self.process_action("start", "app_a")
        self.wait_ready(auth=True)
        self.continue_pending(sid, before, fault_started=started)

    def case_cross_instance(self, sid):
        before = self.pending(sid)
        self.continue_pending(sid, before, server="app_b")

    def case_postgres_restart(self, sid):
        before = self.pending(sid)
        started = time.monotonic()
        self.process_action("restart", "postgres")
        self.wait_ready(auth=True)
        self.continue_pending(sid, before, fault_started=started)

    def case_postgres_outage(self, sid):
        before = self.pending(sid)
        count = self.weather_count()
        started = time.monotonic()
        self.process_action("stop", "postgres")
        try:
            response = self.request("/agent/query", body={"query": "深圳", "session_id": sid})
            self.current.check("explicit_storage_unavailable", response["status"], 503)
            self.current.check("no_weather_side_effect_during_outage", self.weather_count(), count)
        finally:
            self.process_action("start", "postgres")
            self.wait_ready(auth=True)
        self.continue_pending(sid, before, fault_started=started)

    def case_postgres_expiry(self, sid):
        before = self.pending(sid)
        conversations = self.request(f"/agent/conversations?session_id={sid}")["body"].get("total", 0)
        self.sql(f"UPDATE session_records SET expires_at=clock_timestamp()+interval '2 seconds' "
                 f"WHERE user_id={sql_literal(self.users['owner'])} AND session_id={sql_literal(sid)}")
        self.current.actions.append({"kind": "expiry", "backend": "postgresql", "deadline_seconds": 2})
        time.sleep(2.3)
        count = self.weather_count()
        response = self.query("深圳", sid)
        self.current.check("expired_session_does_not_execute", response["body"].get("success"), False)
        self.current.check("expired_fields_not_reused", not response["body"].get("parsed", {}).get("date"))
        self.current.check("no_weather_after_expiry", self.weather_count(), count)
        remaining = self.request(f"/agent/conversations?session_id={sid}")["body"].get("total", 0)
        self.current.check("history_retained_after_expiry", remaining >= conversations > 0)
        self.current.metrics["expected_expiry"] = True

    def anon_seed(self, sid):
        response = self.request("/nl/parse", owner=None, body={"query": "明天下午2点到3点深圳巡检能飞吗", "session_id": sid})
        self.current.check("anonymous_seed_ok", response["status"], 200)
        key = f"reliability:session:anonymous:default_user:{sid}"
        raw = self.redis("GET", key)
        value = json.loads(raw) if raw else None
        self.current.actions.append({"kind": "redis_snapshot", "key": key, "context": value, "ttl": self.redis("TTL", key)})
        return key, value

    def case_redis_expiry(self, sid):
        key, before = self.anon_seed(sid)
        self.redis("PEXPIRE", key, "2000")
        time.sleep(2.3)
        response = self.request("/nl/parse", owner=None, body={"query": "后天呢", "session_id": sid})
        self.current.check("expired_redis_key_removed", self.redis("EXISTS", key), "0")
        self.current.check("expired_redis_requires_fields", response["status"], 422)
        self.current.metrics["expected_expiry"] = True

    def case_redis_outage(self, sid):
        key, before = self.anon_seed(sid)
        started = time.monotonic()
        self.process_action("stop", "redis")
        try:
            response = self.request("/nl/parse", owner=None, body={"query": "后天呢", "session_id": sid})
            self.current.check("explicit_redis_unavailable", response["status"], 503)
            stateless = self.request("/nl/parse", owner=None, body={"query": "深圳明天下午2点到3点巡检能飞吗"})
            self.current.check("stateless_parse_still_works", stateless["status"], 200)
            authenticated = self.query("深圳报备政策", sid + "-independent")
            self.current.check("postgres_session_independent_of_redis", authenticated["body"].get("success"), True)
        finally:
            self.process_action("start", "redis")
        self.anonymous_continue(sid, key, before, started)

    def anonymous_continue(self, sid, key, before, started):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                if self.redis("PING") == "PONG":
                    break
            except RuntimeError:
                pass
            time.sleep(0.2)
        raw = self.redis("GET", key)
        self.current.check("redis_restored_saved_context", json.loads(raw) if raw else None, before)
        response = self.request("/nl/parse", owner=None, body={"query": "后天呢", "session_id": sid})
        self.current.check("redis_continuation_ok", response["status"], 200)
        self.current.check("field:redis_location", response["body"].get("parsed", {}).get("location"), "深圳")
        self.current.metrics.update(restoration_eligible=True, recovery_ms=round((response["client_received_at_monotonic"] - started) * 1000, 3), continuation_latency_ms=response["latency_ms"])
        self.current.metrics["restored"] = response["status"] == 200 and response["body"].get("parsed", {}).get("location") == "深圳" and (json.loads(raw) if raw else None) == before

    def case_redis_restart(self, sid):
        key, before = self.anon_seed(sid)
        self.current.actions.append({"kind": "redis_persistence_config", "appendonly": self.redis("CONFIG", "GET", "appendonly"),
                                     "appendfsync": self.redis("CONFIG", "GET", "appendfsync")})
        started = time.monotonic()
        self.process_action("restart", "redis")
        self.anonymous_continue(sid, key, before, started)

    def case_isolation(self, sid):
        self.control(delay_seconds=0.1)
        try:
            seeded = self.probe([
                {"url": "http://app_a:8000/agent/query", "method": "POST", "token": self.tokens["owner"], "json": {"query": "深圳明天下午2点到3点巡检能飞吗", "session_id": sid}},
                {"url": "http://app_b:8000/agent/query", "method": "POST", "token": self.tokens["other"], "json": {"query": "广州明天下午3点到4点测绘能飞吗", "session_id": sid}},
            ], parallel=True)
        finally:
            self.control(delay_seconds=0)
        self.current.check("different_users_are_not_serialized_together", all(item["body"].get("success") is True for item in seeded))
        a = self.query("时间改成下午4点到5点", sid, owner="owner")
        b = self.query("时间改成下午4点到5点", sid, owner="other", server="app_b")
        self.fields(a, location="深圳", task_type="inspection")
        self.fields(b, location="广州", task_type="survey")
        fresh = self.query("明天下午2点到3点能飞吗", sid + "-fresh")
        self.current.check("separate_session_does_not_inherit_location", not fresh["body"].get("parsed", {}).get("location"))
        denied = self.request(f"/agent/traces/{a['body'].get('trace_id')}", owner="other")
        self.current.check("other_user_cannot_read_trace", denied["status"], 404)
        self.current.metrics["isolation_case"] = True
        self.snapshot(sid, "owner")
        self.snapshot(sid, "other")

    def install_trigger(self, sid, sleep=False):
        body = "PERFORM pg_sleep(30);" if sleep else "RAISE EXCEPTION 'session reliability injected save failure';"
        self.sql(f"CREATE OR REPLACE FUNCTION reliability_session_fault() RETURNS trigger LANGUAGE plpgsql AS $$ "
                 f"BEGIN IF NEW.session_id={sql_literal(sid)} THEN {body} END IF; RETURN NEW; END $$; "
                 "CREATE TRIGGER reliability_session_fault BEFORE INSERT OR UPDATE ON session_records "
                 "FOR EACH ROW EXECUTE FUNCTION reliability_session_fault();")
        self.current.actions.append({"kind": "database_fault", "point": "session_write_after_business_commit", "mode": "sleep" if sleep else "raise"})

    def remove_trigger(self):
        self.sql("DROP TRIGGER IF EXISTS reliability_session_fault ON session_records; DROP FUNCTION IF EXISTS reliability_session_fault();")

    def task_count(self):
        return int(self.sql(f"SELECT count(*) FROM mission_tasks WHERE user_id={sql_literal(self.users['owner'])}"))

    def case_session_save_failure(self, sid):
        before = self.pending(sid)
        count = self.task_count()
        self.install_trigger(sid)
        try:
            response = self.query("帮我创建一个深圳明天下午2点到3点巡检任务", sid)
            self.current.check("business_retained_on_save_failure", response["body"].get("success"), True)
            self.current.check("save_failure_not_acknowledged", any("会话上下文保存失败" in item for item in response["body"].get("warnings", [])))
            self.current.check("exactly_one_task_after_fault", self.task_count() - count, 1)
            self.current.check("previous_acknowledged_session_unchanged", self.snapshot(sid), before)
        finally:
            self.remove_trigger()
        self.continue_pending(sid, before)

    def case_concurrent_update(self, sid):
        self.query("深圳明天下午2点到3点巡检能飞吗", sid)
        self.control(delay_seconds=0.25)
        items = [
            {"url": "http://app_a:8000/agent/query", "method": "POST", "token": self.tokens["owner"], "json": {"query": "地点改成广州", "session_id": sid}},
            {"url": "http://app_b:8000/agent/query", "method": "POST", "token": self.tokens["owner"], "json": {"query": "任务类型改成测绘", "session_id": sid}},
        ]
        try:
            responses = self.probe(items, parallel=True)
        finally:
            self.control(delay_seconds=0)
        successful = [index for index, response in enumerate(responses) if response["body"].get("success") is True]
        busy = [index for index, response in enumerate(responses) if (response["body"].get("fallback") or {}).get("error_code") == "SESSION_BUSY"]
        self.current.check("one_same_session_request_admitted", len(successful), 1)
        self.current.check("other_request_explicitly_rejected", len(busy), 1)
        for index in busy:
            self.query(items[index]["json"]["query"], sid, server="app_b" if index else "app_a")
        stored = self.snapshot(sid)
        self.current.check("field:concurrent_location", (stored or {}).get("location"), "广州")
        self.current.check("field:concurrent_task_type", (stored or {}).get("task_type"), "survey")
        self.current.metrics["concurrent_case"] = True

    def case_crash_before_session_write(self, sid):
        before = self.pending(sid)
        count = self.task_count()
        self.install_trigger(sid, sleep=True)
        started = time.monotonic()
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.request, "/agent/query", body={"query": "帮我创建一个深圳明天下午2点到3点巡检任务", "session_id": sid})
                deadline = time.monotonic() + 15
                sleeping = []
                while time.monotonic() < deadline:
                    sleeping = self.sql_json("SELECT pid,wait_event,query FROM pg_stat_activity WHERE wait_event='PgSleep'")
                    if sleeping:
                        break
                    time.sleep(0.1)
                self.current.check("reached_postcommit_fault_point", bool(sleeping))
                self.current.check("business_committed_before_crash", self.task_count() - count, 1)
                self.docker("kill", "-s", "SIGKILL", "app_a")
                self.current.actions.append({"kind": "process", "action": "SIGKILL_after_business_commit_before_session_write", "active_queries": sleeping})
                self.sql("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE wait_event='PgSleep'")
                self.current.check("interrupted_request_not_acknowledged", future.result()["status"], 0)
        finally:
            self.remove_trigger()
            self.process_action("start", "app_a")
            self.wait_ready(auth=True)
        self.current.check("no_automatic_duplicate_task", self.task_count() - count, 1)
        self.current.check("previous_acknowledged_context_survives", self.snapshot(sid), before)
        self.current.metrics.update(inflight_request_not_replayed=True, recovery_ms=round((time.monotonic() - started) * 1000, 3))

    def run(self):
        try:
            self.docker("up", "-d", "postgres", "redis", "weather", "probe", "app_a")
            self.wait_ready()
            self.account("owner")
            self.account("other")
            self.docker("up", "-d", "app_b")
            self.wait_ready("app_b")
            for iteration in range(1, self.args.repeats + 1):
                for scenario in self.args.scenarios:
                    case = Case(f"SR-{scenario}-{iteration}", scenario, iteration)
                    self.current = case
                    try:
                        getattr(self, f"case_{scenario}")(f"sr-{scenario.replace('_', '-')}-{iteration}")
                    except Exception as exc:
                        case.check("scenario_completed", type(exc).__name__ + ": " + str(exc), "completed")
                    finally:
                        self.current = None
                    result = case.result()
                    self.results.append(result)
                    (self.output / f"{case.id}.json").write_text(json.dumps(redact(result), ensure_ascii=False, indent=2), encoding="utf-8")
                    print(json.dumps({"case": case.id, "passed": result["passed"], "failed_checks": [item["name"] for item in case.checks if not item["passed"]]}), flush=True)
                    self.write_report()
        finally:
            self.current = None
            logs = self.docker("logs", "--no-color", "--timestamps", check=False)
            (self.output / "container-logs.txt").write_text(logs.stdout + logs.stderr, encoding="utf-8")
            if not self.args.keep:
                self.docker("down", "--volumes", "--remove-orphans", check=False)
            self.write_report()

    def write_report(self):
        eligible = [item for item in self.results if item["metrics"].get("restoration_eligible")]
        fields = [check for item in self.results for check in item["checks"] if check["name"].startswith("field:")]
        scenario_results = {}
        for scenario in self.args.scenarios:
            cases = [item for item in self.results if item["scenario"] == scenario]
            values = [item["metrics"]["recovery_ms"] for item in cases if "recovery_ms" in item["metrics"]]
            scenario_results[scenario] = {
                "cases": len(cases), "passed": sum(item["passed"] for item in cases),
                "recovery_ms": {"samples": values, "median": statistics.median(values) if values else None,
                                "max": max(values) if values else None,
                                "p95": sorted(values)[round((len(values) - 1) * 0.95)] if len(values) >= 20 else None},
                "continuation_latency_ms": [item["metrics"]["continuation_latency_ms"] for item in cases if "continuation_latency_ms" in item["metrics"]],
            }
        outcomes = {}
        tool_results = []
        fallback_count = 0
        for case in self.results:
            for action in case["actions"]:
                if action["kind"] != "http":
                    continue
                for request, response in zip(action["requests"], action["responses"]):
                    if not request["url"].endswith("/agent/query"):
                        continue
                    body = response["body"]
                    runtime = body.get("agent_runtime") or {}
                    if response["status"] != 200:
                        outcome = "transport_error" if response["status"] == 0 else "http_error"
                    elif runtime.get("status") == "needs_clarification":
                        outcome = "clarification"
                    elif (body.get("fallback") or {}).get("error_code") == "SESSION_BUSY":
                        outcome = "busy"
                    elif body.get("success"):
                        outcome = "degraded" if body.get("warnings") else "success"
                    else:
                        outcome = "failed"
                    outcomes[outcome] = outcomes.get(outcome, 0) + 1
                    fallback_count += int(bool(runtime.get("fallback_used")))
                    tool_results.extend((body.get("result") or {}).get("tool_results", {}).values())
        report = {
            "run_at": datetime.now(timezone(timedelta(hours=8))).isoformat(), "project": self.project,
            "code_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
            "image": self.args.image, "image_id": self.image_id, "source_sha256": self.source_hashes,
            "repeats": self.args.repeats, "scenarios": self.args.scenarios,
            "configuration": {"authenticated_session": "PostgreSQL", "anonymous_session": "Redis AOF", "app_instances": 2,
                              "parser": "rule", "llm": "disabled", "weather": "real HTTP to deterministic local fixture", "external_network": "disabled"},
            "summary": {"cases": len(self.results), "passed": sum(item["passed"] for item in self.results),
                        "restoration_eligible": len(eligible), "restoration_passed": sum(bool(item["metrics"].get("restored")) for item in eligible),
                        "fields_checked": len(fields), "fields_correct": sum(item["passed"] for item in fields)},
            "by_scenario": scenario_results,
            "observability": {"agent_request_outcomes": outcomes, "legacy_fallback_count": fallback_count,
                              "returned_tool_results": len(tool_results), "successful_tool_results": sum(bool(item.get("success")) for item in tool_results),
                              "failed_tool_results": sum(not item.get("success") for item in tool_results)},
            "results": self.results,
        }
        (self.output / "report.json").write_text(json.dumps(redact(report), ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="drone-low-altitude-agent:session-reliability-validation")
    parser.add_argument("--project")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--scenarios", nargs="+", choices=SCENARIOS, default=SCENARIOS)
    parser.add_argument("--keep", action="store_true", help="Keep the disposable project for diagnosis")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    suite = Suite(args)
    suite.run()
    print(str(suite.output / "report.json"))
    if not suite.results or not all(item["passed"] for item in suite.results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
