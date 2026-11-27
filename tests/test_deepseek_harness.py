"""Validate the live suite itself using fixture model output and no network."""

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


def test_deepseek_scenarios_with_fixture_model_and_real_tools():
    root = Path(__file__).resolve().parents[1]
    # A subprocess ensures every SessionLocal import binds to the temporary DB.
    # This fixture validation never invokes the live runner or a model provider.
    source = r'''
import json
import os
from pathlib import Path
import pytest
class FixtureModel:
    def pytest_configure(self):
        import httpx
        from app.services import llm_task_parser
        from app.services.nl_parser import parse_natural_language_request, NaturalLanguageParseError
        def generate(**kwargs):
            prompt = json.loads(kwargs["user_prompt"])
            try:
                result = parse_natural_language_request(prompt["query"], context=prompt["context"], defer_context_merge=True)
                payload = {"intent": result.intent, **result.parsed}
            except NaturalLanguageParseError as exc:
                payload = {"intent": exc.intent, **exc.parsed, "missing_fields": exc.missing_fields}
            # Fixture extraction is literal for these two cities. Do not use
            # the rule parser's residual free-text locality as a model oracle.
            cities = [city for city in ("深圳", "广州") if city in prompt["query"]]
            if cities:
                payload["location"] = cities[0]
                if payload["intent"] == "create_task":
                    payload["candidate_locations"] = cities
            elif not prompt["context"].get("location"):
                payload.pop("location", None)
                payload.pop("locations", None)
            return json.dumps(payload, ensure_ascii=False)
        llm_task_parser.generate_text = generate
        def forbid_network(*args, **kwargs):
            raise AssertionError("fixture-model suite must never access the network")
        httpx.Client.send = forbid_network
raise SystemExit(pytest.main(["tests/test_deepseek_regression.py", "-q", "--tb=short",
    "--basetemp=" + str(Path(os.environ["DEEPSEEK_EVAL_ISOLATED_ROOT"]) / "pytest-temp")], plugins=[FixtureModel()]))
'''
    # A short path also avoids Windows' legacy 260-character path limit when
    # pytest in a subprocess creates its own per-case directories.
    with TemporaryDirectory(prefix="deepseek-fixture-", dir=root / "data") as directory:
        isolation = Path(directory).resolve()
        output = isolation / "fixture-evidence"
        output.mkdir()
        result = subprocess.run([sys.executable, "-c", source], cwd=root, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=120, env={
            **os.environ, "DATABASE_URL": f"sqlite:///{(isolation / 'regression.db').as_posix()}",
            "SESSION_MEMORY_BACKEND": "database", "LLM_ENABLED": "true", "LLM_PROVIDER": "deepseek",
            "LLM_MODEL": "fixture-model", "LLM_API_KEY": "fixture-no-secret", "NL_PARSER_MODE": "llm",
            "AGENT_RUNTIME_MODE": "loop", "KNOWLEDGE_RETRIEVER": "bm25",
            "KNOWLEDGE_SOURCE_PATH": str(root / "data/knowledge/advice_rules.json"),
            "DEEPSEEK_EVAL_ISOLATED_ROOT": str(isolation), "DEEPSEEK_EVAL_REPORT_DIR": str(output),
            "DEEPSEEK_EVAL_RUN_ID": "fixture-validation-only", "PYTHONIOENCODING": "utf-8",
            "DEEPSEEK_EVAL_MODEL_TRANSPORT": "fixture",
        })
        assert result.returncode == 0, result.stdout + result.stderr
        reports = [json.loads(path.read_text(encoding="utf-8")) for path in output.glob("case-*.json")]
        assert len(reports) == 5
        assert all(row["passed"] for row in reports)
        assert all(row["model_calls"] for row in reports)
        assert all(row["model_transport"] == "fixture" for row in reports)
        assert all(attempt["latency_ms"] >= 0 for row in reports for attempt in row["model_attempts"])
        invalid = next(row for row in reports if row["case_id"] == "test_deepseek_invalid_model_format")
        assert {call["format_fault"] for call in invalid["model_calls"]} == {"json", "schema"}


def test_live_runner_rejects_missing_credentials_before_starting_tests(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([
        sys.executable, str(root / "scripts/deepseek_regression_eval.py"), "--report-dir", str(tmp_path),
    ], cwd=root, capture_output=True, text=True, timeout=15,
        env={**os.environ, "LLM_API_KEY": "", "DEEPSEEK_API_KEY": "", "LLM_MODEL": ""})
    assert result.returncode == 2
    assert not list(tmp_path.iterdir())
