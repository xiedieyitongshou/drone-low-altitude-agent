import re
from dataclasses import dataclass
from datetime import datetime, timedelta

import dateparser

from app.rules.mission_profiles import is_supported_task_type


TASK_TYPE_KEYWORDS = {
    "hover": ["悬停拍摄", "定点悬停", "悬停", "拍摄"],
    "survey": ["低空测绘", "测绘", "航测", "建模"],
    "inspection": ["设备巡检", "巡检", "检查"],
    "cruise": ["低空巡航", "巡航", "巡视"],
}

COMPARE_HINTS = ["哪个", "哪里", "先去哪", "先去哪一个", "排序", "比较", "对比"]
RECOMMEND_HINTS = ["什么时候", "何时", "推荐", "最佳时间", "最适合"]
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
    def __init__(self, message: str, *, missing_fields: list[str] | None = None) -> None:
        super().__init__(message)
        self.missing_fields = missing_fields or []


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

    if intent == "compare":
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
            raise NaturalLanguageParseError("多地点比选请求信息不完整", missing_fields=missing_fields)

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
            ]
        )

        if not merged_location:
            raise NaturalLanguageParseError("推荐请求缺少关键地点信息", missing_fields=["location"])
        if not merged_date:
            warnings.append("未显式识别日期，已默认使用今天")
            merged_date = datetime.now().date().isoformat()

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
            raise NaturalLanguageParseError("评估请求信息不完整", missing_fields=missing_fields)

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
    if len(locations) >= 2 or any(word in text for word in COMPARE_HINTS):
        return "compare"
    if scan_hours or any(word in text for word in RECOMMEND_HINTS):
        return "recommend"
    if has_time_range:
        return "evaluate"
    if fallback_intent:
        return fallback_intent
    raise NaturalLanguageParseError("未识别到明确任务意图", missing_fields=["intent"])


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
    now = datetime.now()

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
        "可以执行吗",
        "适合吗",
        "能飞吗",
        "好吗",
        "请问",
        "帮我",
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
    return any(word in text for word in COMPARE_HINTS + RECOMMEND_HINTS)


def _context_value(context: dict[str, object], key: str, default: object | None = None) -> object | None:
    return context.get(key, default)


def _context_list(context: dict[str, object], key: str) -> list[str]:
    value = context.get(key)
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []
