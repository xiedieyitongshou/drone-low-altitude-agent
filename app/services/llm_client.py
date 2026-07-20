import json
import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class LLMClientConfig:
    enabled: bool
    provider: str
    model: str
    base_url: str
    api_key: str | None
    timeout_seconds: float
    max_tokens: int


def load_llm_config() -> LLMClientConfig:
    return LLMClientConfig(
        enabled=os.getenv("LLM_ENABLED", "false").lower() == "true",
        provider=os.getenv("LLM_PROVIDER", "none").strip().lower(),
        model=os.getenv("LLM_MODEL", "").strip(),
        base_url=os.getenv("LLM_BASE_URL", "").strip().rstrip("/"),
        api_key=os.getenv("LLM_API_KEY") or None,
        timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "20")),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "600")),
    )


def is_llm_enabled() -> bool:
    config = load_llm_config()
    return bool(config.enabled and config.provider != "none" and config.model and config.base_url)


def generate_text(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> str | None:
    config = load_llm_config()
    if not is_llm_enabled():
        return None

    if config.provider not in {"openai_compatible", "openai", "dashscope", "groq", "gemini"}:
        return None

    payload: dict[str, Any] = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens or config.max_tokens,
    }
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    try:
        with httpx.Client(timeout=config.timeout_seconds) as client:
            response = client.post(
                f"{config.base_url}/chat/completions",
                headers=headers,
                content=json.dumps(payload, ensure_ascii=False),
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError):
        return None

    choices = data.get("choices") if isinstance(data, dict) else None
    if not choices:
        return None
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    return content.strip() if isinstance(content, str) and content.strip() else None
