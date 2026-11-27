from pathlib import Path
import sys
import unittest

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.llm_task_parser import LLMParsedTaskPayload, build_parsed_task_request_from_llm_payload
from app.services.nl_parser import NaturalLanguageParseError


@pytest.mark.parametrize("intent,fields,missing", [
    ("evaluate", {"date": "2026-11-28", "start_time": "14:00", "end_time": "16:00", "task_type": "inspection"}, "location"),
    ("recommend", {"date": "2026-11-28", "task_type": "survey"}, "location"),
    ("compare", {"date": "2026-11-28", "start_time": "14:00", "end_time": "16:00", "locations": ["深圳"]}, "locations"),
])
def test_llm_partial_compute_request_preserves_context_for_agent_clarification(intent, fields, missing):
    from app.services.llm_task_parser import LLMParsedTaskPayload, build_parsed_task_request_from_llm_payload

    payload = LLMParsedTaskPayload(intent=intent, **fields)
    for defer in (False, True):
        with pytest.raises(NaturalLanguageParseError) as error:
            build_parsed_task_request_from_llm_payload(payload, query="继续", defer_context_merge=defer)
        assert error.value.intent == intent
        assert error.value.parser_source == "llm"
        for key, value in fields.items():
            assert error.value.parsed[key] == value
        assert missing in error.value.missing_fields


class LLMTaskParserTestCase(unittest.TestCase):
    def test_knowledge_llm_can_fill_a_literal_locality_but_cannot_replace_it(self) -> None:
        query = "请查当地报备政策，范围是庐阳"
        for city, expected in (("庐阳", "庐阳"), ("广州", None)):
            payload = LLMParsedTaskPayload.model_validate({
                "intent": "knowledge", "city": city, "knowledge_evidence": {"city": "庐阳"},
            })
            result = build_parsed_task_request_from_llm_payload(payload, query=query, defer_context_merge=True)
            self.assertEqual(result.parsed.get("city"), expected)

    def test_knowledge_ambiguous_cities_still_require_clarification(self) -> None:
        payload = LLMParsedTaskPayload.model_validate({
            "intent": "knowledge", "city": "深圳", "knowledge_evidence": {"city": "深圳"},
        })
        with self.assertRaises(NaturalLanguageParseError) as raised:
            build_parsed_task_request_from_llm_payload(payload, query="深圳和广州的报备政策", defer_context_merge=True)
        self.assertEqual(raised.exception.missing_fields, ["city"])

    def test_knowledge_fields_need_evidence_and_keep_unknown_warning_state(self) -> None:
        query = "请查深圳2026年11月20日的黄色预警政策"
        payload = LLMParsedTaskPayload.model_validate({
            "intent": "knowledge", "city": "深圳", "as_of": "2026-11-20", "task_type": "survey",
            "knowledge_evidence": {"city": "深圳", "as_of": "2026年11月20日"},
        })
        result = build_parsed_task_request_from_llm_payload(payload, query=query, defer_context_merge=True)
        self.assertEqual(result.parsed["city"], "深圳")
        self.assertEqual(result.parsed["as_of"], "2026-11-20")
        self.assertNotIn("task_type", result.parsed)
        self.assertNotIn("warning_levels", result.parsed)
        self.assertEqual(result.parsed["query"], query)

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

    def test_create_task_can_defer_missing_fields_and_defaults_to_agent(self) -> None:
        payload = LLMParsedTaskPayload.model_validate(
            {"intent": "create_task", "location": "深圳湾", "date": "2026-07-26"}
        )
        query = "帮我创建一个深圳湾明天任务"
        with self.assertRaises(NaturalLanguageParseError):
            build_parsed_task_request_from_llm_payload(payload, query=query)

        result = build_parsed_task_request_from_llm_payload(
            payload,
            query=query,
            context={"task_type": "survey", "start_time": "14:00", "end_time": "17:00"},
            defer_context_merge=True,
        )

        self.assertEqual(result.intent, "create_task")
        self.assertEqual(result.parsed["location"], "深圳湾")
        self.assertTrue({"task_type", "start_time", "end_time"}.isdisjoint(result.parsed))

    def test_confidence_accepts_model_label(self) -> None:
        payload = LLMParsedTaskPayload.model_validate(
            {
                "intent": "evaluate",
                "location": "深圳湾",
                "date": "2026-07-26",
                "start_time": "09:00",
                "end_time": "11:00",
                "confidence": "low",
            }
        )

        self.assertEqual(payload.confidence, 0.3)


if __name__ == "__main__":
    unittest.main()
