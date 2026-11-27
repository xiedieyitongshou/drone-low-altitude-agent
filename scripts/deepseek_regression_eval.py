"""Opt-in real-model regression, always launched in a disposable database process."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, help="Optional local credentials file; never copied to reports.")
    parser.add_argument("--model", help="DeepSeek model to test, otherwise use LLM_MODEL.")
    parser.add_argument("--report-dir", type=Path, default=ROOT / "data/eval-reports/deepseek")
    args = parser.parse_args()
    if args.env_file:
        from dotenv import load_dotenv

        if not args.env_file.is_file():
            parser.error("--env-file does not exist")
        load_dotenv(args.env_file, override=False)
    model = args.model or os.getenv("LLM_MODEL", "").strip()
    if not model or not (os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")):
        parser.error("Set LLM_MODEL and LLM_API_KEY/DEEPSEEK_API_KEY; real-model regression cannot run without them.")
    run_id = uuid4().hex
    output = args.report_dir.resolve() / run_id
    output.mkdir(parents=True)
    with TemporaryDirectory(prefix="drone-deepseek-") as isolation:
        isolated_root = Path(isolation).resolve()
        env = {
            **os.environ,
            "DATABASE_URL": f"sqlite:///{(isolated_root / 'regression.db').as_posix()}",
            "SESSION_MEMORY_BACKEND": "database", "AUTO_MIGRATE_ON_STARTUP": "false",
            "LLM_ENABLED": "true", "LLM_PROVIDER": "deepseek", "LLM_MODEL": model,
            "NL_PARSER_MODE": "llm", "AGENT_RUNTIME_MODE": "loop",
            "KNOWLEDGE_RETRIEVER": "bm25",
            "KNOWLEDGE_SOURCE_PATH": str(ROOT / "data/knowledge/advice_rules.json"),
            "DEEPSEEK_EVAL_ISOLATED_ROOT": str(isolated_root),
            "DEEPSEEK_EVAL_REPORT_DIR": str(output), "DEEPSEEK_EVAL_RUN_ID": run_id,
            "DEEPSEEK_EVAL_MODEL_TRANSPORT": "deepseek",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        }
        result = subprocess.run([
            sys.executable, "-m", "pytest", "tests/test_deepseek_regression.py", "-q",
            f"--junitxml={output / 'junit.xml'}",
        ], cwd=ROOT, env=env)
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in output.glob("case-*.json")]
    passed = result.returncode == 0 and len(reports) == 5 and all(
        row["passed"] and row.get("model_transport") == "deepseek" for row in reports
    )
    metadata = {
        "run_id": run_id, "model": model, "provider": "deepseek",
        "base_url": env.get("LLM_BASE_URL") or "https://api.deepseek.com",
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "working_tree_changed": bool(subprocess.check_output(["git", "diff", "--name-only"], cwd=ROOT, text=True).strip()),
        "weather": "fixed local provider responses", "database": "disposable SQLite",
        "model_scope": "task parser only; explanation and relevance-review LLM calls disabled",
        "total_cases": len(reports), "passed_cases": sum(bool(row["passed"]) for row in reports),
        "real_model_responses": sum(len(row["model_calls"]) for row in reports),
        "passed": passed,
    }
    (output / "summary.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"DeepSeek regression: {metadata['passed_cases']}/5; reports: {output}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
