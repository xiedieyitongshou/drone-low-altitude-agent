import json
import re
from typing import Any

from app.services.llm_client import generate_text, is_llm_enabled


TASK_PARSER_SYSTEM_PROMPT = """你是无人机低空任务请求解析器。
只输出 JSON，不要输出解释。
字段只能包含 intent、location、locations、date、start_time、end_time、task_type、scan_hours、min_window_hours、top_k、comparison_mode、purpose。
intent 只能是 evaluate、recommend、compare。
task_type 只能是 cruise、inspection、hover、survey。
无法确定的字段不要编造，直接省略。"""


def parse_task_request_with_llm(
    query: str,
    *,
    context: dict[str, object] | None = None,
) -> dict[str, Any] | None:
    if not is_llm_enabled():
        return None

    user_prompt = json.dumps(
        {
            "query": query,
            "context": context or {},
            "output": "strict_json",
        },
        ensure_ascii=False,
    )
    content = generate_text(
        system_prompt=TASK_PARSER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0,
        max_tokens=500,
    )
    if not content:
        return None
    return _extract_json_object(content)


def _extract_json_object(content: str) -> dict[str, Any] | None:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.S)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    return data if isinstance(data, dict) else None
