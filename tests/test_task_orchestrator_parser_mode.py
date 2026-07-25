from pathlib import Path
import sys
import unittest
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.nl_parser import NaturalLanguageParseError, ParsedTaskRequest
from app.services.task_orchestrator import _parse_task_query


class TaskOrchestratorParserModeTestCase(unittest.TestCase):
    def test_rule_mode_uses_rule_parser(self) -> None:
        with patch.dict("os.environ", {"NL_PARSER_MODE": "rule"}, clear=False):
            parsed = _parse_task_query("深圳明天下午2点到5点可以飞吗")

        self.assertEqual(parsed.intent, "evaluate")
        self.assertEqual(parsed.parser_source, "rule")

    def test_llm_mode_uses_llm_parser(self) -> None:
        llm_result = ParsedTaskRequest(
            intent="recommend",
            target_endpoint="/cruise/recommend",
            parsed={
                "location": "深圳",
                "date": "2026-07-26",
                "task_type": "cruise",
                "purpose": "demo",
                "scan_hours": 72,
                "min_window_hours": 2,
            },
            warnings=[],
            parser_source="llm",
        )

        with patch.dict("os.environ", {"NL_PARSER_MODE": "llm"}, clear=False), patch(
            "app.services.task_orchestrator.parse_natural_language_request_with_llm",
            return_value=llm_result,
        ):
            parsed = _parse_task_query("深圳未来72小时最佳窗口")

        self.assertEqual(parsed.intent, "recommend")
        self.assertEqual(parsed.parser_source, "llm")

    def test_llm_mode_raises_when_llm_unavailable(self) -> None:
        with patch.dict("os.environ", {"NL_PARSER_MODE": "llm"}, clear=False), patch(
            "app.services.task_orchestrator.parse_natural_language_request_with_llm",
            return_value=None,
        ):
            with self.assertRaises(NaturalLanguageParseError):
                _parse_task_query("深圳未来72小时最佳窗口")

    def test_hybrid_mode_falls_back_to_rule_parser(self) -> None:
        with patch.dict("os.environ", {"NL_PARSER_MODE": "hybrid"}, clear=False), patch(
            "app.services.task_orchestrator.parse_natural_language_request_with_llm",
            side_effect=NaturalLanguageParseError("bad llm output", missing_fields=["location"]),
        ):
            parsed = _parse_task_query("深圳明天下午2点到5点可以飞吗")

        self.assertEqual(parsed.intent, "evaluate")
        self.assertEqual(parsed.parser_source, "llm_fallback_rule")
        self.assertTrue(any("LLM parser failed" in item for item in parsed.warnings))

    def test_unknown_mode_falls_back_to_rule_parser(self) -> None:
        with patch.dict("os.environ", {"NL_PARSER_MODE": "unknown"}, clear=False):
            parsed = _parse_task_query("深圳明天下午2点到5点可以飞吗")

        self.assertEqual(parsed.intent, "evaluate")
        self.assertEqual(parsed.parser_source, "rule")
        self.assertTrue(any("Unsupported NL_PARSER_MODE" in item for item in parsed.warnings))


if __name__ == "__main__":
    unittest.main()
