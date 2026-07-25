from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.llm_task_parser import LLMParsedTaskPayload, build_parsed_task_request_from_llm_payload
from app.services.nl_parser import NaturalLanguageParseError


class LLMTaskParserTestCase(unittest.TestCase):
    def test_build_evaluate_request(self) -> None:
        payload = LLMParsedTaskPayload.model_validate(
            {
                "intent": "evaluate",
                "location": "深圳湾",
                "date": "2026-07-26",
                "start_time": "14:00",
                "end_time": "17:00",
                "task_type": "cruise",
            }
        )

        result = build_parsed_task_request_from_llm_payload(payload, query="深圳湾明天下午可以飞吗")

        self.assertEqual(result.intent, "evaluate")
        self.assertEqual(result.target_endpoint, "/cruise/evaluate")
        self.assertEqual(result.parser_source, "llm")
        self.assertEqual(result.parsed["location"], "深圳湾")

    def test_build_recommend_request_defaults_window_fields(self) -> None:
        payload = LLMParsedTaskPayload.model_validate(
            {
                "intent": "recommend",
                "location": "深圳",
                "date": "2026-07-26",
                "task_type": "survey",
            }
        )

        result = build_parsed_task_request_from_llm_payload(payload, query="深圳未来最佳测绘窗口")

        self.assertEqual(result.intent, "recommend")
        self.assertEqual(result.target_endpoint, "/cruise/recommend")
        self.assertEqual(result.parsed["scan_hours"], 72)
        self.assertEqual(result.parsed["min_window_hours"], 2)
        self.assertEqual(result.parsed["task_type"], "survey")

    def test_build_compare_request_clamps_top_k(self) -> None:
        payload = LLMParsedTaskPayload.model_validate(
            {
                "intent": "compare",
                "locations": ["深圳湾", "南山区"],
                "date": "2026-07-26",
                "start_time": "13:00",
                "end_time": "18:00",
                "task_type": "inspection",
                "top_k": 5,
            }
        )

        result = build_parsed_task_request_from_llm_payload(payload, query="两个地点哪个适合巡检")

        self.assertEqual(result.intent, "compare")
        self.assertEqual(result.target_endpoint, "/cruise/compare")
        self.assertEqual(result.parsed["top_k"], 2)
        self.assertEqual(result.parsed["locations"], ["深圳湾", "南山区"])

    def test_context_fills_missing_task_type(self) -> None:
        payload = LLMParsedTaskPayload.model_validate(
            {
                "intent": "evaluate",
                "location": "深圳湾",
                "date": "2026-07-26",
                "start_time": "14:00",
                "end_time": "17:00",
            }
        )

        result = build_parsed_task_request_from_llm_payload(
            payload,
            query="那这个时间可以吗",
            context={"task_type": "survey"},
        )

        self.assertTrue(result.context_used)
        self.assertEqual(result.parsed["task_type"], "survey")

    def test_missing_required_fields_raise_parse_error(self) -> None:
        payload = LLMParsedTaskPayload.model_validate(
            {
                "intent": "evaluate",
                "date": "2026-07-26",
                "task_type": "cruise",
            }
        )

        with self.assertRaises(NaturalLanguageParseError) as raised:
            build_parsed_task_request_from_llm_payload(payload, query="明天可以飞吗")

        self.assertIn("location", raised.exception.missing_fields)
        self.assertIn("start_time", raised.exception.missing_fields)
        self.assertIn("end_time", raised.exception.missing_fields)


if __name__ == "__main__":
    unittest.main()
