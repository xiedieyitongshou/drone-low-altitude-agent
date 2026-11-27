import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("script,dataset,report", [
    ("tool_calling_eval", "agent/cases.json", "tool_calling_eval"),
    ("multi_turn_state_eval", "agent/multi_turn_cases.json", "multi_turn_state_eval"),
    ("failure_recovery_eval", "agent/failure_recovery_cases.json", "failure_recovery_eval"),
    ("rag_eval", "rag/cases.json", "rag_eval"),
])
@pytest.mark.parametrize("empty", [False, True])
def test_agent_eval_cli_fails_bad_or_empty_cases_and_preserves_reports(tmp_path, script, dataset, report, empty):
    cases = json.loads((ROOT / "evals" / dataset).read_text(encoding="utf-8-sig"))[:1]
    if empty:
        cases = []
    elif script == "tool_calling_eval":
        cases[0]["expected_intent"] = "deliberately_incorrect"
    elif script == "multi_turn_state_eval":
        cases[0]["turns"][0]["expected_intent"] = "deliberately_incorrect"
    elif script == "failure_recovery_eval":
        cases[0]["expected"]["error_code"] = "deliberately_incorrect"
    else:
        cases[0]["expected_knowledge_ids"] = ["deliberately_incorrect"]
    source = tmp_path / "cases.json"
    source.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "reports"
    command = [sys.executable, str(ROOT / "scripts" / f"{script}.py"), "--cases", str(source), "--report-dir", str(output)]
    if script == "rag_eval":
        command.extend(["--retrievers", "hybrid"])
    result = subprocess.run(
        command,
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45,
        env={**os.environ, "LLM_ENABLED": "false", "NL_PARSER_MODE": "rule", "PYTHONIOENCODING": "utf-8",
             "DATABASE_URL": f"sqlite:///{(tmp_path / 'unused.db').as_posix()}"},
    )
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads((output / f"{report}.json").read_text(encoding="utf-8"))
    if script != "rag_eval":
        assert payload["summary"]["pass_rate"] < 1.0
    assert (output / f"{report}.md").exists()
