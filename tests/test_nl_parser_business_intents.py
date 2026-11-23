import pytest

from app.services.nl_parser import NaturalLanguageParseError, parse_natural_language_request


@pytest.mark.parametrize("query", ["重试", "再试一次", "重试。"])
def test_retry_input_reuses_context_instead_of_becoming_a_location(query):
    context = {"intent": "evaluate", "location": "广州", "date": "2026-11-23",
               "start_time": "14:00", "end_time": "17:00", "task_type": "inspection"}
    parsed = parse_natural_language_request(query, context=context)
    assert parsed.intent == "evaluate"
    assert parsed.parsed["location"] == "广州"
    assert parsed.parsed["task_type"] == "inspection"


@pytest.mark.parametrize("day", ["2026-11-22", "2026/11/22", "2026年11月22日"])
def test_calendar_date_is_not_used_as_the_time_range(day):
    result = parse_natural_language_request(f"深圳{day}下午2点到3点巡航能飞吗", defer_context_merge=True)
    assert result.parsed["date"] == "2026-11-22"
    assert result.parsed["start_time"] == "14:00"
    assert result.parsed["end_time"] == "15:00"


def test_rule_parser_detects_history_query():
    result = parse_natural_language_request("查一下我上次深圳任务记录")

    assert result.intent == "history"
    assert result.target_endpoint == "/agent/conversations"
    assert result.parsed["mode"] == "list"
    assert result.parsed["keyword"] == "深圳"


def test_rule_parser_detects_knowledge_policy_query():
    result = parse_natural_language_request("深圳无人机巡检政策有什么要注意")

    assert result.intent == "knowledge"
    assert result.target_endpoint == "/knowledge/advice/retrieve"
    assert result.parsed["task_type"] == "inspection"
    assert result.parsed["city"] == "深圳"
    assert result.parsed["top_k"] == 3


def test_rule_parser_detects_knowledge_sop_query_without_location():
    result = parse_natural_language_request("遇到强风预警时无人机巡航 SOP 怎么处理")

    assert result.intent == "knowledge"
    assert result.parsed["task_type"] == "cruise"
    assert result.parsed["query"] == "遇到强风预警时无人机巡航 SOP 怎么处理"
    assert "city" not in result.parsed


@pytest.mark.parametrize(
    ("query", "city"),
    [
        ("深圳，空域核查政策", "深圳"),
        ("深圳市无人机作业报备政策有哪些注意事项？", "深圳"),
        ("想了解广州市无人机作业报备政策", "广州"),
        ("请问浙江省杭州市无人机报备政策", "杭州"),
        ("无人机作业报备政策有哪些注意事项？", None),
        ("持续降雨时怎么办，有哪些作业建议？", None),
    ],
)
def test_rule_parser_extracts_city_only_from_location_mentions(query, city):
    result = parse_natural_language_request(query)

    assert result.intent == "knowledge"
    assert result.parsed["query"] == query
    assert result.parsed.get("city") == city


def test_rule_parser_detects_risk_explanation_query():
    result = parse_natural_language_request(
        "为什么刚才判高风险，依据是什么",
        context={
            "intent": "evaluate",
            "task_type": "inspection",
            "overall_decision": "禁飞",
            "risk_reasons": ["风速偏高"],
        },
    )

    assert result.intent == "explain"
    assert result.target_endpoint == "/agent/rules/explain"
    assert result.context_used is True
    assert result.parsed["task_type"] == "inspection"
    assert result.parsed["overall_decision"] == "禁飞"


def test_rule_parser_supports_context_based_modify_query():
    result = parse_natural_language_request(
        "把地点改成佛山，时间还是明天下午",
        context={
            "intent": "evaluate",
            "task_type": "inspection",
            "date": "2026-08-02",
            "start_time": "13:00",
            "end_time": "18:00",
        },
    )

    assert result.intent == "evaluate"
    assert result.context_used is True
    assert result.parsed["location"] == "佛山"
    assert result.parsed["task_type"] == "inspection"


def test_rule_parser_supports_task_type_modify_query_without_fake_location():
    result = parse_natural_language_request(
        "任务类型改成测绘",
        context={
            "intent": "evaluate",
            "location": "深圳",
            "date": "2026-08-03",
            "start_time": "13:00",
            "end_time": "18:00",
            "task_type": "inspection",
        },
    )

    assert result.intent == "evaluate"
    assert result.parsed["location"] == "深圳"
    assert result.parsed["task_type"] == "survey"


def test_rule_parser_supports_time_modify_query_without_fake_location():
    result = parse_natural_language_request(
        "时间改成后天下午",
        context={
            "intent": "evaluate",
            "location": "深圳",
            "date": "2026-08-03",
            "start_time": "09:00",
            "end_time": "11:00",
            "task_type": "inspection",
        },
    )

    assert result.intent == "evaluate"
    assert result.parsed["location"] == "深圳"
    assert result.parsed["start_time"] == "13:00"
    assert result.parsed["end_time"] == "18:00"


def test_rule_parser_still_requires_missing_fields_for_evaluate():
    with pytest.raises(NaturalLanguageParseError) as exc_info:
        parse_natural_language_request("明天下午能飞吗")

    assert exc_info.value.missing_fields == ["location"]
