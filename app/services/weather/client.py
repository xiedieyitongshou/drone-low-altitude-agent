import logging
import time
from typing import Any

import httpx

from app.services.weather.exceptions import (
    WeatherAuthenticationError,
    WeatherRequestError,
    WeatherResponseError,
)


logger = logging.getLogger(__name__)


class HttpClient:
    def __init__(
        self,
        api_key: str,
        timeout_seconds: float,
        max_retries: int,
        retry_backoff_seconds: float,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout_seconds),
            headers={"X-QW-Api-Key": api_key},
        )

    def get(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        last_exception: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._client.get(url, params=params)
                self._raise_for_status(response)
                return response.json()
            except (httpx.HTTPError, WeatherResponseError) as exc:
                last_exception = exc
                logger.warning(
                    "Weather API request failed",
                    extra={"url": url, "attempt": attempt, "error": str(exc)},
                )
                if attempt == self._max_retries:
                    break
                time.sleep(self._retry_backoff_seconds * attempt)

        raise WeatherRequestError(f"Weather API request failed after retries: {url}") from last_exception

    def close(self) -> None:
        self._client.close()

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code in (401, 403):
            raise WeatherAuthenticationError("Weather API authentication failed")
        if response.status_code >= 500:
            raise WeatherResponseError(f"Weather API server error: {response.status_code}")
        if response.status_code >= 400:
            raise WeatherResponseError(f"Weather API request error: {response.status_code}")
