import re
from dataclasses import dataclass
from datetime import datetime, timedelta

import dateparser

from app.rules.mission_profiles import is_supported_task_type
from app.utils.timezone import now_in_app_timezone


TASK_TYPE_KEYWORDS = {
    "hover": ["悬停拍摄", "定点悬停", "悬停", "拍摄"],
    "survey": ["低空测绘", "测绘", "航测", "建模"],
    "inspection": ["设备巡检", "巡检", "检查"],
    "cruise": ["低空巡航", "巡航", "巡视"],
}

COMPARE_HINTS = ["哪个", "哪里", "先去哪", "先去哪一个", "排序", "比较", "对比"]
RECOMMEND_HINTS = ["什么时候", "何时", "推荐", "最佳时间", "最适合"]
EVALUATE_HINTS = ["可以飞吗", "能飞吗", "适合飞吗", "适合吗", "可以执行吗"]
HISTORY_HINTS = ["历史", "历史记录", "上次", "之前", "以前", "查记录", "查询记录", "任务记录", "会话记录"]
KNOWLEDGE_HINTS = ["政策", "规则", "规定", "知识库", "注意事项", "建议", "怎么处理", "SOP", "标准流程", "FAQ", "风险说明"]
EXPLAIN_HINTS = ["为什么", "为何", "依据是什么", "规则来源", "判定依据", "为什么判", "为什么不能飞", "为什么高风险", "解释一下"]
MODIFY_HINTS = ["改成", "换成", "改为", "换为", "还是", "不变"]
CREATE_TASK_HINTS = ["创建任务", "新建任务", "建个任务", "建立任务", "创建一个", "新建一个"]
EVALUATE_TASK_HINTS = ["评估这个任务", "评估一下这个任务", "评估任务", "这个任务能飞吗", "这个任务可以飞吗"]
RECOMMEND_TASK_HINTS = ["推荐窗口", "推荐一下窗口", "推荐任务窗口", "给这个任务推荐", "这个任务什么时候"]
SELECT_WINDOW_HINTS = ["选第一个窗口", "选择第一个窗口", "就选第一个", "选第二个窗口", "选择第二个窗口", "就选第二个", "选第三个窗口", "选择第三个窗口", "就选第三个"]
PREFLIGHT_TASK_HINTS = ["执行前复核", "执行前检查", "起飞前复核", "起飞前检查", "再检查一次", "再复核一次"]
TIME_RANGE_PATTERNS = [
    re.compile(
        r"(?P<start_period>凌晨|早上|上午|中午|下午|晚上)?\s*"
        r"(?P<start_hour>\d{1,2})(?:(?:[:点时])(?P<start_minute>\d{1,2})?)?\s*"
        r"(?:到|至|—|-|~|～)\s*"
        r"(?P<end_period>凌晨|早上|上午|中午|下午|晚上)?\s*"
        r"(?P<end_hour>\d{1,2})(?:(?:[:点时])(?P<end_minute>\d{1,2})?)?"
    )
]
DATE_PATTERN = re.compile(
    r"(今天|明天|后天|大后天|本周[一二三四五六日天]|下周[一二三四五六日天]|周[一二三四五六日天]|"
    r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日号]?|\d{1,2}月\d{1,2}[日号]?)"
)
SCAN_HOURS_PATTERN = re.compile(r"(?:未来|接下来)(?P<hours>\d{1,3})小时")
TASK_ID_PATTERN = re.compile(r"(?:task[_-]?)?(?P<task_id>[0-9a-fA-F]{8,64})")
WEEKDAY_MAP = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
PERIOD_WINDOWS = {
    "凌晨": ("00:00", "06:00"),
    "早上": ("06:00", "09:00"),
    "上午": ("06:00", "12:00"),
    "中午": ("11:00", "13:00"),
    "下午": ("13:00", "18:00"),
    "晚上": ("18:00", "24:00"),
}


class NaturalLanguageParseError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        missing_fields: list[str] | None = None,
        intent: str | None = None,
        target_endpoint: str | None = None,
        parsed: dict[str, object] | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.missing_fields = missing_fields or []
        self.intent = intent
        self.target_endpoint = target_endpoint
        self.parsed = parsed or {}
        self.warnings = warnings or []


@dataclass
class ParsedTaskRequest:
    intent: str
    target_endpoint: str
    parsed: dict[str, object]
    warnings: list[str]
    context_used: bool = False
    parser_source: str = "rule"


def parse_natural_language_request(
    query: str,
    *,
    context: dict[str, object] | None = None,
) -> ParsedTaskRequest:
    text = _normalize_query(query)
    if not text:
        raise NaturalLanguageParseError("未检测到有效输入内容", missing_fields=["query"])

    task_type, task_type_detected = _detect_task_type(text)
    scan_hours = _detect_scan_hours(text)
    start_time, end_time = _detect_time_range(text)
    if not start_time or not end_time:
        start_time, end_time = _detect_period_window(text)
    date_text = _detect_date(text)
    locations = _detect_locations(text)
    context = context or {}

    if not any([locations, date_text, start_time, end_time, scan_hours, task_type_detected, _has_intent_hint(text)]):
        raise NaturalLanguageParseError("未检测到可解析的任务要素", missing_fields=["location", "date"])

    mission_result = _parse_mission_task_intent(
        query=query,
        text=text,
        context=context,
        locations=locations,
        date_text=date_text,
        start_time=start_time,
        end_time=end_time,
        task_type=task_type,
        task_type_detected=task_type_detected,
        scan_hours=scan_hours,
    )
    if mission_result is not None:
        return mission_result

    intent = _detect_intent(
        text=text,
        locations=locations,
        scan_hours=scan_hours,
        has_time_range=bool(start_time and end_time),
        fallback_intent=str(context.get("intent")) if context.get("intent") else None,
    )

    warnings: list[str] = []
    context_used = False
    parsed: dict[str, object]

    merged_task_type = task_type if task_type_detected else _context_value(context, "task_type", "cruise")

    if intent == "history":
        keyword = _detect_history_keyword(query, locations)
        parsed = {
            "mode": "list",
            "keyword": keyword,
            "page": 1,
            "page_size": 10,
        }
        target_endpoint = "/agent/conversations"
    elif intent == "explain":
        context_used = bool(context)
        parsed = {
            "query": query,
            "task_type": task_type if task_type_detected else _context_value(context, "task_type", "cruise"),
            "overall_decision": _context_value(context, "overall_decision"),
            "risk_reasons": _context_value(context, "risk_reasons") or _context_value(context, "summary_risk_factors"),
        }
        parsed = {key: value for key, value in parsed.items() if value not in (None, "", [])}
        target_endpoint = "/agent/rules/explain"
    elif intent == "knowledge":
        merged_task_type = task_type if task_type_detected else _context_value(context, "task_type", "cruise")
        city = locations[0] if locations else _context_value(context, "city") or _context_value(context, "location")
        context_used = not locations and bool(city)
        parsed = {
            "query": query,
            "task_type": merged_task_type,
            "city": city,
            "top_k": 3,
        }
        parsed = {key: value for key, value in parsed.items() if value not in (None, "", [])}
        target_endpoint = "/knowledge/advice/retrieve"
    elif intent == "compare":
        merged_locations = locations or _context_list(context, "locations")
        merged_date = date_text or _context_value(context, "date")
        merged_start_time = start_time or _context_value(context, "start_time")
        merged_end_time = end_time or _context_value(context, "end_time")
        context_used = any(
            [
                not locations and bool(merged_locations),
                not date_text and bool(merged_date),
                not start_time and bool(merged_start_time),
                not end_time and bool(merged_end_time),
                not task_type_detected and bool(context.get("task_type")),
            ]
        )

        missing_fields: list[str] = []
        if len(merged_locations) < 2:
            missing_fields.append("locations")
        if not merged_date:
            missing_fields.append("date")
        if not merged_start_time:
            missing_fields.append("start_time")
        if not merged_end_time:
            missing_fields.append("end_time")
        if missing_fields:
            raise NaturalLanguageParseError(
                "多地点比选请求信息不完整",
                missing_fields=missing_fields,
                intent="compare",
                target_endpoint="/cruise/compare",
                parsed={
                    "locations": merged_locations,
                    "date": merged_date,
                    "start_time": merged_start_time,
                    "end_time": merged_end_time,
                    "task_type": merged_task_type,
                    "purpose": query,
                    "top_k": min(3, len(merged_locations)) if merged_locations else 3,
                    "comparison_mode": "default",
                },
                warnings=warnings,
            )

        parsed = {
            "locations": merged_locations,
            "date": merged_date,
            "start_time": merged_start_time,
            "end_time": merged_end_time,
            "task_type": merged_task_type,
            "purpose": query,
            "top_k": min(3, len(merged_locations)),
            "comparison_mode": "default",
        }
        target_endpoint = "/cruise/compare"
    elif intent == "recommend":
        merged_location = (locations[0] if locations else None) or _context_value(context, "location")
        merged_date = date_text or _context_value(context, "date")
        merged_scan_hours = scan_hours or _context_value(context, "scan_hours", 72)
        context_used = any(
            [
                not locations and bool(merged_location),
                not date_text and bool(merged_date),
                scan_hours is None and merged_scan_hours != 72,
                not task_type_detected and bool(context.get("task_type")),
            ]
        )

        if not merged_location:
            raise NaturalLanguageParseError(
                "推荐请求缺少关键地点信息",
                missing_fields=["location"],
                intent="recommend",
                target_endpoint="/cruise/recommend",
                parsed={
                    "location": merged_location,
                    "date": merged_date,
                    "task_type": merged_task_type,
                    "purpose": query,
                    "scan_hours": int(merged_scan_hours),
                    "min_window_hours": 2,
                },
                warnings=warnings,
            )
        if not merged_date:
            warnings.append("未显式识别日期，已默认使用今天")
            merged_date = now_in_app_timezone().date().isoformat()

        parsed = {
            "location": merged_location,
            "date": merged_date,
            "task_type": merged_task_type,
            "purpose": query,
            "scan_hours": int(merged_scan_hours),
            "min_window_hours": 2,
        }
        target_endpoint = "/cruise/recommend"
    else:
        merged_location = (locations[0] if locations else None) or _context_value(context, "location")
        merged_date = date_text or _context_value(context, "date")
        merged_start_time = start_time or _context_value(context, "start_time")
        merged_end_time = end_time or _context_value(context, "end_time")
        context_used = any(
            [
                not locations and bool(merged_location),
                not date_text and bool(merged_date),
                not start_time and bool(merged_start_time),
                not end_time and bool(merged_end_time),
                not task_type_detected and bool(context.get("task_type")),
            ]
        )

        missing_fields: list[str] = []
        if not merged_location:
            missing_fields.append("location")
        if not merged_date:
            missing_fields.append("date")
        if not merged_start_time:
            missing_fields.append("start_time")
        if not merged_end_time:
            missing_fields.append("end_time")
        if missing_fields:
            raise NaturalLanguageParseError(
                "评估请求信息不完整",
                missing_fields=missing_fields,
                intent="evaluate",
                target_endpoint="/cruise/evaluate",
                parsed={
                    "location": merged_location,
                    "date": merged_date,
                    "start_time": merged_start_time,
                    "end_time": merged_end_time,
                    "task_type": merged_task_type,
                    "purpose": query,
                },
                warnings=warnings,
            )

        parsed = {
            "location": merged_location,
            "date": merged_date,
            "start_time": merged_start_time,
            "end_time": merged_end_time,
            "task_type": merged_task_type,
            "purpose": query,
        }
        target_endpoint = "/cruise/evaluate"

    return ParsedTaskRequest(
        intent=intent,
        target_endpoint=target_endpoint,
        parsed=parsed,
        warnings=warnings,
        context_used=context_used,
        parser_source="rule",
    )


def _normalize_query(query: str) -> str:
    text = re.sub(r"\s+", "", query or "")
    return text.strip("，。！？,.!?")


def _detect_task_type(text: str) -> tuple[str, bool]:
    for task_type, keywords in TASK_TYPE_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return task_type, True
    return "cruise", False


def _detect_intent(
    *,
    text: str,
    locations: list[str],
    scan_hours: int | None,
    has_time_range: bool,
    fallback_intent: str | None,
) -> str:
    if any(word in text for word in HISTORY_HINTS):
        return "history"
    if any(word in text for word in EXPLAIN_HINTS):
        return "explain"
    if any(word in text for word in KNOWLEDGE_HINTS):
        return "knowledge"
    if fallback_intent and any(word in text for word in MODIFY_HINTS):
        return fallback_intent
    if len(locations) >= 2 or any(word in text for word in COMPARE_HINTS):
        return "compare"
    if scan_hours or any(word in text for word in RECOMMEND_HINTS):
        return "recommend"
    if has_time_range:
        return "evaluate"
    if any(word in text for word in EVALUATE_HINTS):
        return "evaluate"
    if fallback_intent:
        return fallback_intent
    raise NaturalLanguageParseError("未识别到明确任务意图", missing_fields=["intent"])


def _parse_mission_task_intent(
    *,
    query: str,
    text: str,
    context: dict[str, object],
    locations: list[str],
    date_text: str | None,
    start_time: str | None,
    end_time: str | None,
    task_type: str,
    task_type_detected: bool,
    scan_hours: int | None,
) -> ParsedTaskRequest | None:
    intent = _detect_mission_task_intent(text)
    if intent is None:
        return None

    if intent == "create_task":
        parsed = {
            "task_title": _detect_task_title(query, locations, task_type),
            "location": locations[0] if locations else None,
            "date": date_text,
            "start_time": start_time,
            "end_time": end_time,
            "task_type": task_type if task_type_detected else _context_value(context, "task_type", "cruise"),
            "purpose": query,
            "candidate_locations": locations[1:] if len(locations) > 1 else [],
        }
        missing_fields = [
            field
            for field in ["location", "date", "start_time", "end_time", "task_type"]
            if parsed.get(field) in (None, "", [])
        ]
        if missing_fields:
            raise NaturalLanguageParseError(
                "任务创建请求信息不完整",
                missing_fields=missing_fields,
                intent="create_task",
                target_endpoint="/tasks",
                parsed={key: value for key, value in parsed.items() if value not in (None, "", [])},
            )
        return ParsedTaskRequest(
            intent="create_task",
            target_endpoint="/tasks",
            parsed={key: value for key, value in parsed.items() if value not in (None, "", [])},
            warnings=[],
        )

    task_id, used_context = _resolve_task_id(text, context)
    window_rank = _detect_window_rank(text)
    parsed = {
        "task_id": task_id,
        "task_title": _context_value(context, "current_task_title") or _context_value(context, "task_title"),
        "purpose": query,
    }
    if intent == "recommend_task":
        parsed["scan_hours"] = scan_hours or _context_value(context, "scan_hours", 72)
        parsed["min_window_hours"] = _context_value(context, "min_window_hours", 2)
    if intent == "select_task_window":
        parsed["window_rank"] = window_rank or _context_value(context, "selected_window_rank")

    required_fields = ["task_id", "window_rank"] if intent == "select_task_window" else ["task_id"]
    missing_fields = [field for field in required_fields if parsed.get(field) in (None, "", [])]
    target_endpoint = {
        "evaluate_task": "/tasks/{task_id}/evaluate",
        "recommend_task": "/tasks/{task_id}/recommend",
        "select_task_window": "/tasks/{task_id}/select-window",
        "preflight_check_task": "/tasks/{task_id}/preflight-check",
    }[intent]
    if missing_fields:
        raise NaturalLanguageParseError(
            "任务单操作缺少任务上下文",
            missing_fields=missing_fields,
            intent=intent,
            target_endpoint=target_endpoint,
            parsed={key: value for key, value in parsed.items() if value not in (None, "", [])},
        )
    return ParsedTaskRequest(
        intent=intent,
        target_endpoint=target_endpoint,
        parsed={key: value for key, value in parsed.items() if value not in (None, "", [])},
        warnings=[],
        context_used=used_context,
    )


def _detect_mission_task_intent(text: str) -> str | None:
    if any(word in text for word in CREATE_TASK_HINTS):
        return "create_task"
    if any(word in text for word in PREFLIGHT_TASK_HINTS):
        return "preflight_check_task"
    if any(word in text for word in SELECT_WINDOW_HINTS):
        return "select_task_window"
    if any(word in text for word in RECOMMEND_TASK_HINTS):
        return "recommend_task"
    if any(word in text for word in EVALUATE_TASK_HINTS):
        return "evaluate_task"
    return None


def _resolve_task_id(text: str, context: dict[str, object]) -> tuple[str | None, bool]:
    match = TASK_ID_PATTERN.search(text)
    if match:
        return match.group("task_id"), False
    for key in ["current_task_id", "task_id"]:
        value = context.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip(), True
    return None, False


def _detect_window_rank(text: str) -> int | None:
    rank_words = {
        "第一个": 1,
        "第一": 1,
        "1": 1,
        "第二个": 2,
        "第二": 2,
        "2": 2,
        "第三个": 3,
        "第三": 3,
        "3": 3,
    }
    for word, rank in rank_words.items():
        if word in text:
            return rank
    return None


def _detect_task_title(query: str, locations: list[str], task_type: str) -> str:
    if locations:
        return f"{locations[0]}{task_type}任务"
    return query[:80]


def _detect_scan_hours(text: str) -> int | None:
    match = SCAN_HOURS_PATTERN.search(text)
    if not match:
        return None
    return int(match.group("hours"))


def _detect_date(text: str) -> str | None:
    match = DATE_PATTERN.search(text)
    if not match:
        return None
    fragment = match.group(0)
    now = now_in_app_timezone()

    relative_days = {
        "今天": 0,
        "明天": 1,
        "后天": 2,
        "大后天": 3,
    }
    if fragment in relative_days:
        return (now.date() + timedelta(days=relative_days[fragment])).isoformat()

    if fragment.startswith("本周"):
        weekday = WEEKDAY_MAP[fragment[-1]]
        current_weekday = now.weekday()
        delta = weekday - current_weekday
        return (now.date() + timedelta(days=delta)).isoformat()

    if fragment.startswith("下周"):
        weekday = WEEKDAY_MAP[fragment[-1]]
        current_weekday = now.weekday()
        delta = weekday - current_weekday + 7
        return (now.date() + timedelta(days=delta)).isoformat()

    if fragment.startswith("周"):
        weekday = WEEKDAY_MAP[fragment[-1]]
        current_weekday = now.weekday()
        delta = weekday - current_weekday
        if delta < 0:
            delta += 7
        return (now.date() + timedelta(days=delta)).isoformat()

    parsed = dateparser.parse(
        fragment,
        languages=["zh"],
        settings={
            "PREFER_DATES_FROM": "future",
            "TIMEZONE": "Asia/Shanghai",
            "RETURN_AS_TIMEZONE_AWARE": False,
            "RELATIVE_BASE": now,
        },
    )
    if parsed is None:
        return None
    return parsed.date().isoformat()


def _detect_time_range(text: str) -> tuple[str | None, str | None]:
    for pattern in TIME_RANGE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        start_period = match.group("start_period")
        end_period = match.group("end_period") or start_period
        start_time = _build_time_text(
            period=start_period,
            hour_text=match.group("start_hour"),
            minute_text=match.group("start_minute"),
        )
        end_time = _build_time_text(
            period=end_period,
            hour_text=match.group("end_hour"),
            minute_text=match.group("end_minute"),
        )
        return start_time, end_time
    return None, None


def _detect_period_window(text: str) -> tuple[str | None, str | None]:
    for period, window in PERIOD_WINDOWS.items():
        if period in text:
            return window
    return None, None


def _build_time_text(*, period: str | None, hour_text: str | None, minute_text: str | None) -> str:
    hour = int(hour_text or "0")
    minute = int(minute_text or "0")
    if hour == 24:
        return "24:00"

    if period in {"下午", "晚上"} and hour < 12:
        hour += 12
    elif period == "中午" and hour < 11:
        hour += 12
    elif period == "凌晨" and hour == 12:
        hour = 0

    return f"{hour:02d}:{minute:02d}"


def _detect_locations(text: str) -> list[str]:
    cleaned = text

    for task_keywords in TASK_TYPE_KEYWORDS.values():
        for keyword in task_keywords:
            cleaned = cleaned.replace(keyword, "")

    cleaned = SCAN_HOURS_PATTERN.sub("", cleaned)
    cleaned = DATE_PATTERN.sub("", cleaned)
    for pattern in TIME_RANGE_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    for period in PERIOD_WINDOWS:
        cleaned = cleaned.replace(period, "")

    stop_words = [
        "什么时间最适合执行任务",
        "什么时候最适合执行任务",
        "什么时候最适合",
        "最佳时间",
        "最适合执行任务",
        "多个地点中",
        "先去哪一个",
        "哪个更适合先去",
        "哪个更适合",
        "哪里更适合",
        "可以飞吗",
        "适合飞吗",
        "可以执行吗",
        "适合吗",
        "能飞吗",
        "好吗",
        "请问",
        "帮我",
        "任务类型改成",
        "任务类型换成",
        "任务类型改为",
        "任务类型换为",
        "任务类型",
        "类型",
        "时间改成",
        "时间换成",
        "时间改为",
        "时间换为",
        "时间",
        "地点改成",
        "地点换成",
        "地点改为",
        "地点换为",
        "改成",
        "换成",
        "改为",
        "换为",
        "时间还是",
        "时间不变",
        "还是",
        "不变",
        "查一下",
        "查询",
        "一下",
        "创建任务",
        "新建任务",
        "建个任务",
        "建立任务",
        "创建一个",
        "新建一个",
        "评估这个任务",
        "评估任务",
        "推荐窗口",
        "选择窗口",
        "执行前复核",
        "执行前检查",
        "起飞前复核",
        "起飞前检查",
        "再检查一次",
        "再复核一次",
        "选第一个窗口",
        "选择第一个窗口",
        "就选第一个",
        "选第二个窗口",
        "选择第二个窗口",
        "就选第二个",
        "选第三个窗口",
        "选择第三个窗口",
        "就选第三个",
        "有哪些",
        "有什么",
        "要注意",
        "注意事项",
        "建议",
        "知识库",
        "政策",
        "规则",
        "规定",
        "历史记录",
        "任务记录",
        "会话记录",
        "历史",
        "上次",
        "之前",
        "以前",
        "我的",
        "我",
        "任务",
        "执行",
        "低空",
        "无人机",
        "那",
        "呢",
    ]
    for word in stop_words:
        cleaned = cleaned.replace(word, "")

    cleaned = cleaned.strip("在去到从把给问请看一下，。！？,.!?")
    if not cleaned:
        return []

    if any(sep in cleaned for sep in ["、", "，", ",", "和", "及", "以及"]):
        parts = re.split(r"[、，,]|以及|及|和", cleaned)
        return [item.strip() for item in parts if _is_valid_location(item.strip())]

    return [cleaned] if _is_valid_location(cleaned) else []


def _is_valid_location(value: str) -> bool:
    if not value or len(value) < 2:
        return False
    if value.isdigit():
        return False
    if is_supported_task_type(value):
        return False
    return True


def _has_intent_hint(text: str) -> bool:
    return any(
        word in text
        for word in (
            COMPARE_HINTS
            + RECOMMEND_HINTS
            + EVALUATE_HINTS
            + HISTORY_HINTS
            + KNOWLEDGE_HINTS
            + EXPLAIN_HINTS
            + CREATE_TASK_HINTS
            + EVALUATE_TASK_HINTS
            + RECOMMEND_TASK_HINTS
            + SELECT_WINDOW_HINTS
            + PREFLIGHT_TASK_HINTS
        )
    )


def _detect_history_keyword(query: str, locations: list[str]) -> str | None:
    if locations:
        return locations[0]
    text = _normalize_query(query)
    for word in HISTORY_HINTS + ["帮我", "查一下", "查询", "一下", "我的", "我"]:
        text = text.replace(word, "")
    text = text.strip("在去到从把给问请看一下，。！？,.!?")
    return text or None


def _context_value(context: dict[str, object], key: str, default: object | None = None) -> object | None:
    return context.get(key, default)


def _context_list(context: dict[str, object], key: str) -> list[str]:
    value = context.get(key)
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []
