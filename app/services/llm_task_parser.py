import json
import re
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.rules.mission_profiles import is_supported_task_type, normalize_task_type
from app.schemas import CruiseEvaluateRequest, MultiLocationComparisonRequest, RecommendationRequest
from app.services.llm_client import generate_text, is_llm_enabled
from app.services.nl_parser import NaturalLanguageParseError, ParsedTaskRequest
from app.utils.timezone import now_in_app_timezone


ALLOWED_MISSING_FIELDS = {
    "intent",
    "task_id",
    "task_title",
    "location",
    "locations",
    "date",
    "start_time",
    "end_time",
    "task_type",
    "window_rank",
}
PERIOD_WINDOWS = {
    "\u51cc\u6668": ("00:00", "06:00"),
    "\u65e9\u4e0a": ("06:00", "09:00"),
    "\u4e0a\u5348": ("06:00", "12:00"),
    "\u4e2d\u5348": ("11:00", "13:00"),
    "\u4e0b\u5348": ("13:00", "18:00"),
    "\u665a\u4e0a": ("18:00", "24:00"),
}
REQUIRED_FIELDS_BY_INTENT = {
    "evaluate": {"location", "date", "start_time", "end_time"},
    "recommend": {"location", "date"},
    "compare": {"locations", "date", "start_time", "end_time"},
    "create_task": {"location", "date", "start_time", "end_time", "task_type"},
    "evaluate_task": {"task_id"},
    "recommend_task": {"task_id"},
    "select_task_window": {"task_id", "window_rank"},
    "preflight_check_task": {"task_id"},
}

TASK_PARSER_SYSTEM_PROMPT = (
    "Do not think step by step. Do not explain. Output the final JSON immediately.\n"
    "\u4f60\u662f\u65e0\u4eba\u673a\u4f4e\u7a7a\u4f5c\u4e1a\u4efb\u52a1\u7684"
    "\u81ea\u7136\u8bed\u8a00\u89e3\u6790\u5668\u3002\n"
    "\u4f60\u7684\u552f\u4e00\u4efb\u52a1\u662f\u628a\u7528\u6237\u4e2d\u6587"
    "\u81ea\u7136\u8bed\u8a00\u8f6c\u6362\u4e3a\u4e25\u683c JSON\u3002\n\n"
    "\u89c4\u5219\uff1a\n"
    "1. \u53ea\u8f93\u51fa\u4e00\u4e2a JSON object\uff0c\u4e0d\u8981\u8f93\u51fa Markdown\u3001"
    "\u89e3\u91ca\u3001\u4ee3\u7801\u5757\u6216\u989d\u5916\u6587\u672c\u3002\n"
    "2. intent \u53ea\u80fd\u662f evaluate\u3001recommend\u3001compare\u3001create_task\u3001evaluate_task\u3001recommend_task\u3001select_task_window\u3001preflight_check_task\u3002\n"
    "3. task_type \u53ea\u80fd\u662f cruise\u3001inspection\u3001hover\u3001survey\u3002\n"
    "4. date \u5fc5\u987b\u8f93\u51fa YYYY-MM-DD\u3002\n"
    "5. start_time \u548c end_time \u5fc5\u987b\u8f93\u51fa HH:MM\uff0cend_time \u5141\u8bb8 24:00\u3002\n"
    "6. \u65e0\u6cd5\u786e\u5b9a\u7684\u5b57\u6bb5\u4e0d\u8981\u7f16\u9020\uff0c"
    "\u653e\u5165 missing_fields\u3002\n"
    "7. \u53ef\u4ee5\u4f7f\u7528 context \u8865\u5168\u7528\u6237\u7701\u7565\u7684\u4fe1\u606f\uff0c"
    "\u4f46\u5f53\u524d query \u660e\u786e\u51fa\u73b0\u7684\u5b57\u6bb5\u4f18\u5148\u3002\n"
    "8. \u53ea\u505a\u4efb\u52a1\u53c2\u6570\u89e3\u6790\uff0c\u4e0d\u5224\u65ad\u662f\u5426"
    "\u9002\u98de\uff0c\u4e0d\u8f93\u51fa\u5b89\u5168\u7ed3\u8bba\u3002\n\n"
    "9. Do not output null optional fields. Omit fields that are not needed for the selected intent.\n"
    "10. missing_fields should only include required fields for the selected intent.\n\n"
    "\u610f\u56fe\u5b9a\u4e49\uff1a\n"
    "- evaluate\uff1a\u7528\u6237\u8be2\u95ee\u67d0\u4e2a\u5730\u70b9\u67d0\u4e2a"
    "\u65f6\u95f4\u6bb5\u662f\u5426\u9002\u5408\u98de\u884c\u3002\n"
    "- recommend\uff1a\u7528\u6237\u8be2\u95ee\u67d0\u5730\u70b9\u672a\u6765\u4e00\u6bb5"
    "\u65f6\u95f4\u5185\u7684\u6700\u4f73\u6267\u884c\u7a97\u53e3\u3002\n"
    "- compare\uff1a\u7528\u6237\u8be2\u95ee\u591a\u4e2a\u5730\u70b9\u4e2d\u54ea\u4e2a"
    "\u66f4\u9002\u5408\u6216\u8981\u6c42\u6392\u5e8f\u3002\n\n"
    "\u4efb\u52a1\u7c7b\u578b\u6620\u5c04\uff1a\n"
    "- \u5de1\u822a\u3001\u5de1\u89c6\u3001\u65e5\u5e38\u5de1\u822a -> cruise\n"
    "- \u5de1\u68c0\u3001\u8bbe\u5907\u5de1\u68c0\u3001\u68c0\u67e5 -> inspection\n"
    "- \u60ac\u505c\u3001\u5b9a\u70b9\u60ac\u505c\u3001\u60ac\u505c\u62cd\u6444\u3001"
    "\u62cd\u6444 -> hover\n"
    "- \u6d4b\u7ed8\u3001\u4f4e\u7a7a\u6d4b\u7ed8\u3001\u822a\u6d4b\u3001"
    "\u5efa\u6a21 -> survey\n\n"
    "\u8f93\u51fa\u5b57\u6bb5\u53ea\u5141\u8bb8\u5305\u542b\uff1a\n"
    "intent, task_id, task_title, location, locations, candidate_locations, date, start_time, end_time, task_type, "
    "scan_hours, min_window_hours, top_k, comparison_mode, purpose, window_rank, "
    "missing_fields, confidence"
)
TASK_PARSER_RETRY_SYSTEM_PROMPT = (
    "Return only valid JSON. No analysis. No markdown. No reasoning text.\n"
    "Schema: {\"intent\":\"evaluate|recommend|compare|create_task|evaluate_task|recommend_task|select_task_window|preflight_check_task\","
    "\"task_id\":\"string\",\"task_title\":\"string\",\"location\":\"string\","
    "\"locations\":[\"string\"],\"candidate_locations\":[\"string\"],\"date\":\"YYYY-MM-DD\",\"start_time\":\"HH:MM\","
    "\"end_time\":\"HH:MM\",\"task_type\":\"cruise|inspection|hover|survey\","
    "\"scan_hours\":72,\"min_window_hours\":2,\"top_k\":3,"
    "\"comparison_mode\":\"default\",\"purpose\":\"string\",\"window_rank\":1,\"missing_fields\":[]}.\n"
    "For recommend, start_time and end_time are not required. For compare, infer afternoon as 13:00-18:00."
)


class LLMParsedTaskPayload(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    intent: Literal[
        "evaluate",
        "recommend",
        "compare",
        "create_task",
        "evaluate_task",
        "recommend_task",
        "select_task_window",
        "preflight_check_task",
    ] | None = None
    task_id: str | None = None
    task_title: str | None = None
    location: str | None = None
    locations: list[str] = Field(default_factory=list)
    candidate_locations: list[str] = Field(default_factory=list)
    date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    task_type: str | None = None
    scan_hours: int | None = None
    min_window_hours: int | None = None
    top_k: int | None = None
    comparison_mode: str | None = "default"
    purpose: str | None = None
    window_rank: int | None = None
    missing_fields: list[str] = Field(default_factory=list)
    confidence: float | None = None

    @field_validator("location")
    @classmethod
    def normalize_location(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("locations")
    @classmethod
    def normalize_locations(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        locations: list[str] = []
        for item in value:
            location = str(item).strip()
            if location and location not in seen:
                locations.append(location)
                seen.add(location)
        return locations

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("date must use YYYY-MM-DD format") from exc
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value == "24:00":
            return value
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError as exc:
            raise ValueError("time must use HH:MM format") from exc
        return value

    @field_validator("task_type")
    @classmethod
    def validate_task_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_task_type(value)
        if not is_supported_task_type(normalized):
            raise ValueError("task_type must be one of: cruise, inspection, hover, survey")
        return normalized

    @field_validator("scan_hours", "min_window_hours", "top_k")
    @classmethod
    def validate_positive_int(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("value must be positive")
        return value

    @field_validator("missing_fields")
    @classmethod
    def normalize_missing_fields(cls, value: list[str]) -> list[str]:
        return [field for field in value if field in ALLOWED_MISSING_FIELDS]

    @model_validator(mode="after")
    def sync_location_fields(self) -> "LLMParsedTaskPayload":
        if self.location and not self.locations:
            self.locations = [self.location]
        if not self.location and self.locations:
            self.location = self.locations[0]
        return self


def parse_natural_language_request_with_llm(
    query: str,
    *,
    context: dict[str, object] | None = None,
) -> ParsedTaskRequest | None:
    raw_payload = parse_task_request_with_llm(query, context=context)
    if raw_payload is None:
        return None

    try:
        payload = LLMParsedTaskPayload.model_validate(raw_payload)
    except ValidationError as exc:
        raise NaturalLanguageParseError(
            "大模型解析结果格式不合法",
            missing_fields=_validation_missing_fields(exc),
        ) from exc

    return build_parsed_task_request_from_llm_payload(payload, query=query, context=context)


def parse_task_request_with_llm(
    query: str,
    *,
    context: dict[str, object] | None = None,
) -> dict[str, Any] | None:
    """Return the raw JSON object produced by the LLM, kept for debugging compatibility."""

    if not is_llm_enabled():
        return None

    user_prompt = json.dumps(
        {
            "query": query,
            "context": context or {},
            "current_date": now_in_app_timezone().date().isoformat(),
            "output": "strict_json",
        },
        ensure_ascii=False,
    )
    content = generate_text(
        system_prompt=TASK_PARSER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0,
        max_tokens=2000,
    )
    if not content:
        content = generate_text(
            system_prompt=TASK_PARSER_RETRY_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0,
            max_tokens=3000,
        )
    if not content:
        return None
    return _extract_json_object(content)


def build_parsed_task_request_from_llm_payload(
    payload: LLMParsedTaskPayload,
    *,
    query: str,
    context: dict[str, object] | None = None,
) -> ParsedTaskRequest:
    context = context or {}
    warnings: list[str] = []
    context_used = False

    if payload.intent is None:
        raise NaturalLanguageParseError("大模型未识别到明确任务意图", missing_fields=["intent"])

    task_type, used_task_context = _merge_value(payload.task_type, context, "task_type", default="cruise")
    context_used = context_used or used_task_context

    if payload.intent in {
        "create_task",
        "evaluate_task",
        "recommend_task",
        "select_task_window",
        "preflight_check_task",
    }:
        parsed, target_endpoint, used_task_context = _build_mission_task_payload(payload, query=query, context=context)
        context_used = context_used or used_task_context
        missing_fields = [field for field in REQUIRED_FIELDS_BY_INTENT[payload.intent] if parsed.get(field) in (None, "", [])]
        if missing_fields:
            raise NaturalLanguageParseError(
                "LLM parsed mission task request is incomplete",
                missing_fields=missing_fields,
                intent=payload.intent,
                target_endpoint=target_endpoint,
                parsed=parsed,
            )
        return ParsedTaskRequest(
            intent=payload.intent,
            target_endpoint=target_endpoint,
            parsed=parsed,
            warnings=_missing_field_warnings(payload.intent, payload.missing_fields),
            context_used=context_used,
            parser_source="llm",
        )

    if payload.intent == "evaluate":
        location, used_location_context = _merge_value(payload.location, context, "location")
        task_date, used_date_context = _merge_value(payload.date, context, "date")
        start_time, used_start_context = _merge_value(payload.start_time, context, "start_time")
        end_time, used_end_context = _merge_value(payload.end_time, context, "end_time")
        start_time, end_time = _fill_period_window(query, start_time, end_time)
        context_used = context_used or any(
            [used_location_context, used_date_context, used_start_context, used_end_context]
        )

        missing_fields = _missing_fields(
            {
                "location": location,
                "date": task_date,
                "start_time": start_time,
                "end_time": end_time,
            }
        )
        if missing_fields:
            raise NaturalLanguageParseError("大模型解析的评估请求信息不完整", missing_fields=missing_fields)

        parsed = {
            "location": location,
            "date": task_date,
            "start_time": start_time,
            "end_time": end_time,
            "task_type": task_type,
            "purpose": payload.purpose or query,
        }
        CruiseEvaluateRequest.model_validate(parsed)
        target_endpoint = "/cruise/evaluate"

    elif payload.intent == "recommend":
        location, used_location_context = _merge_value(payload.location, context, "location")
        task_date, used_date_context = _merge_value(payload.date, context, "date")
        context_used = context_used or used_location_context or used_date_context
        scan_hours = payload.scan_hours or _context_int(context, "scan_hours") or 72
        min_window_hours = payload.min_window_hours or 2

        if not task_date:
            task_date = now_in_app_timezone().date().isoformat()
            warnings.append("未显式识别日期，已默认使用今天")

        missing_fields = _missing_fields({"location": location, "date": task_date})
        if missing_fields:
            raise NaturalLanguageParseError("大模型解析的推荐请求信息不完整", missing_fields=missing_fields)

        parsed = {
            "location": location,
            "date": task_date,
            "task_type": task_type,
            "purpose": payload.purpose or query,
            "scan_hours": int(scan_hours),
            "min_window_hours": int(min_window_hours),
        }
        RecommendationRequest.model_validate(parsed)
        target_endpoint = "/cruise/recommend"

    else:
        locations, used_locations_context = _merge_locations(payload.locations, context)
        task_date, used_date_context = _merge_value(payload.date, context, "date")
        start_time, used_start_context = _merge_value(payload.start_time, context, "start_time")
        end_time, used_end_context = _merge_value(payload.end_time, context, "end_time")
        start_time, end_time = _fill_period_window(query, start_time, end_time)
        context_used = context_used or any(
            [used_locations_context, used_date_context, used_start_context, used_end_context]
        )

        missing_fields = _missing_fields(
            {
                "date": task_date,
                "start_time": start_time,
                "end_time": end_time,
            }
        )
        if len(locations) < 2:
            missing_fields.insert(0, "locations")
        if missing_fields:
            raise NaturalLanguageParseError("大模型解析的多地点比选请求信息不完整", missing_fields=missing_fields)

        top_k = payload.top_k or min(3, len(locations))
        parsed = {
            "locations": locations,
            "date": task_date,
            "start_time": start_time,
            "end_time": end_time,
            "task_type": task_type,
            "purpose": payload.purpose or query,
            "top_k": min(int(top_k), len(locations)),
            "comparison_mode": payload.comparison_mode or "default",
        }
        MultiLocationComparisonRequest.model_validate(parsed)
        target_endpoint = "/cruise/compare"

    warnings.extend(_missing_field_warnings(payload.intent, payload.missing_fields))
    return ParsedTaskRequest(
        intent=payload.intent,
        target_endpoint=target_endpoint,
        parsed=parsed,
        warnings=warnings,
        context_used=context_used,
        parser_source="llm",
    )


def _build_mission_task_payload(
    payload: LLMParsedTaskPayload,
    *,
    query: str,
    context: dict[str, object],
) -> tuple[dict[str, object], str, bool]:
    current_task_id, used_task_id_context = _merge_value(
        payload.task_id,
        context,
        "current_task_id",
    )
    if not current_task_id:
        current_task_id, used_legacy_task_id_context = _merge_value(payload.task_id, context, "task_id")
        used_task_id_context = used_task_id_context or used_legacy_task_id_context
    current_task_title, used_title_context = _merge_value(payload.task_title, context, "current_task_title")
    if not current_task_title:
        current_task_title, used_legacy_title_context = _merge_value(payload.task_title, context, "task_title")
        used_title_context = used_title_context or used_legacy_title_context
    task_type, used_task_type_context = _merge_value(payload.task_type, context, "task_type", default="cruise")
    context_used = used_task_id_context or used_title_context or used_task_type_context

    if payload.intent == "create_task":
        parsed = {
            "task_title": payload.task_title or current_task_title or _default_task_title(payload, query=query),
            "location": payload.location,
            "date": payload.date,
            "start_time": payload.start_time,
            "end_time": payload.end_time,
            "task_type": task_type,
            "purpose": payload.purpose or query,
            "candidate_locations": list(payload.candidate_locations or payload.locations or []),
        }
        target_endpoint = "/tasks"
    elif payload.intent == "select_task_window":
        parsed = {
            "task_id": current_task_id,
            "task_title": current_task_title,
            "window_rank": payload.window_rank,
            "purpose": payload.purpose or query,
        }
        target_endpoint = "/tasks/{task_id}/select-window"
    else:
        parsed = {
            "task_id": current_task_id,
            "task_title": current_task_title,
            "purpose": payload.purpose or query,
        }
        suffix = {
            "evaluate_task": "evaluate",
            "recommend_task": "recommend",
            "preflight_check_task": "preflight-check",
        }[payload.intent]
        target_endpoint = f"/tasks/{{task_id}}/{suffix}"

    return {key: value for key, value in parsed.items() if value not in (None, "", [])}, target_endpoint, context_used


def _default_task_title(payload: LLMParsedTaskPayload, *, query: str) -> str:
    if payload.location:
        return f"{payload.location}{payload.task_type or 'cruise'}任务"
    return query[:80]


def _extract_json_object(content: str) -> dict[str, Any] | None:
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    return data if isinstance(data, dict) else None


def _merge_value(
    value: object | None,
    context: dict[str, object],
    key: str,
    *,
    default: object | None = None,
) -> tuple[object | None, bool]:
    if _has_value(value):
        return value, False
    context_value = context.get(key)
    if _has_value(context_value):
        return context_value, True
    return default, False


def _merge_locations(
    locations: list[str],
    context: dict[str, object],
) -> tuple[list[str], bool]:
    if locations:
        return locations, False
    context_locations = context.get("locations")
    if isinstance(context_locations, list):
        merged = [str(item).strip() for item in context_locations if str(item).strip()]
        if merged:
            return merged, True
    context_location = context.get("location")
    if _has_value(context_location):
        return [str(context_location)], True
    return [], False


def _has_value(value: object | None) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    return True


def _context_int(context: dict[str, object], key: str) -> int | None:
    value = context.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _missing_fields(values: dict[str, object | None]) -> list[str]:
    return [key for key, value in values.items() if not _has_value(value)]


def _fill_period_window(
    query: str,
    start_time: object | None,
    end_time: object | None,
) -> tuple[object | None, object | None]:
    if _has_value(start_time) and _has_value(end_time):
        return start_time, end_time
    for period, window in PERIOD_WINDOWS.items():
        if period in query:
            return start_time or window[0], end_time or window[1]
    return start_time, end_time


def _missing_field_warnings(intent: str, missing_fields: list[str]) -> list[str]:
    required_fields = REQUIRED_FIELDS_BY_INTENT.get(intent, set())
    relevant_missing_fields = [field for field in missing_fields if field in required_fields]
    if not relevant_missing_fields:
        return []
    return [f"大模型标记缺失字段：{', '.join(relevant_missing_fields)}"]


def _validation_missing_fields(exc: ValidationError) -> list[str]:
    fields: list[str] = []
    for error in exc.errors():
        loc = error.get("loc", [])
        if loc:
            fields.append(str(loc[0]))
    return fields
