import json
import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx


logger = logging.getLogger(__name__)

OPENAI_COMPATIBLE_PROVIDERS = {"openai_compatible", "openai", "deepseek", "dashscope", "groq"}
DEFAULT_BASE_URLS = {
    "deepseek": "https://api.deepseek.com",
    "openai": "https://api.openai.com/v1",
}


@dataclass(frozen=True)
class LLMClientConfig:
    enabled: bool
    provider: str
    model: str
    base_url: str
    api_key: str | None
    timeout_seconds: float
    max_tokens: int


class LLMClientError(RuntimeError):
    """Raised when the LLM client cannot complete a request."""


def load_llm_config() -> LLMClientConfig:
    provider = os.getenv("LLM_PROVIDER", "none").strip().lower()
    base_url = os.getenv("LLM_BASE_URL", "").strip().rstrip("/") or DEFAULT_BASE_URLS.get(provider, "")
    api_key = os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or None

    return LLMClientConfig(
        enabled=os.getenv("LLM_ENABLED", "false").lower() == "true",
        provider=provider,
        model=os.getenv("LLM_MODEL", "").strip(),
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "20")),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "600")),
    )


def is_llm_enabled() -> bool:
    config = load_llm_config()
    return bool(
        config.enabled
        and config.provider != "none"
        and config.model
        and config.base_url
        and config.api_key
    )


def generate_text(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> str | None:
    config = load_llm_config()
    if not _is_config_usable(config):
        logger.info(
            "LLM generation skipped",
            extra={
                "enabled": config.enabled,
                "provider": config.provider,
                "has_model": bool(config.model),
                "has_base_url": bool(config.base_url),
                "has_api_key": bool(config.api_key),
            },
        )
        return None

    try:
        return generate_text_or_raise(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            config=config,
        )
    except LLMClientError as exc:
        logger.warning("LLM generation failed: %s", exc)
        return None


def generate_text_or_raise(
    *,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    config: LLMClientConfig | None = None,
) -> str:
    active_config = config or load_llm_config()
    if not _is_config_usable(active_config):
        raise LLMClientError("LLM config is incomplete or disabled")

    if active_config.provider not in OPENAI_COMPATIBLE_PROVIDERS:
        raise LLMClientError(f"unsupported LLM provider: {active_config.provider}")

    payload: dict[str, Any] = {
        "model": active_config.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens or active_config.max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {active_config.api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=active_config.timeout_seconds) as client:
            response = client.post(
                f"{active_config.base_url}/chat/completions",
                headers=headers,
                content=json.dumps(payload, ensure_ascii=False),
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        raise LLMClientError(f"provider returned HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise LLMClientError(f"request failed: {exc}") from exc
    except ValueError as exc:
        raise LLMClientError("provider returned invalid JSON") from exc

    choices = data.get("choices") if isinstance(data, dict) else None
    if not choices:
        raise LLMClientError("provider response has no choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise LLMClientError("provider response has empty message content")
    return content.strip()


def _is_config_usable(config: LLMClientConfig) -> bool:
    return bool(
        config.enabled
        and config.provider != "none"
        and config.model
        and config.base_url
        and config.api_key
    )
