import os
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import load_environment
from app.services.weather.client import HttpClient
from app.services.weather.exceptions import (
    LocationNotFoundError,
    WeatherAuthenticationError,
    WeatherResponseError,
)
from app.services.weather.schemas import (
    GeoLocation,
    HourlyWeatherResponse,
    WeatherWarningResponse,
)

load_environment()


class QWeatherConfig(BaseModel):
    api_key: str = Field(default_factory=lambda: os.getenv("QWEATHER_API_KEY", ""))
    geo_base_url: str = Field(
        default_factory=lambda: os.getenv("QWEATHER_GEO_BASE_URL", "https://geoapi.qweather.com")
    )
    weather_base_url: str = Field(
        default_factory=lambda: os.getenv("QWEATHER_WEATHER_BASE_URL", "https://devapi.qweather.com")
    )
    warning_base_url: str = Field(
        default_factory=lambda: os.getenv(
            "QWEATHER_WARNING_BASE_URL",
            os.getenv("QWEATHER_WEATHER_BASE_URL", "https://devapi.qweather.com"),
        )
    )
    timeout_seconds: float = Field(default_factory=lambda: float(os.getenv("QWEATHER_TIMEOUT_SECONDS", "10")))
    max_retries: int = Field(default_factory=lambda: int(os.getenv("QWEATHER_MAX_RETRIES", "3")))
    retry_backoff_seconds: float = Field(
        default_factory=lambda: float(os.getenv("QWEATHER_RETRY_BACKOFF_SECONDS", "1"))
    )
    lang: str = Field(default_factory=lambda: os.getenv("QWEATHER_LANG", "zh"))


class QWeatherService:
    def __init__(self, config: QWeatherConfig | None = None) -> None:
        self.config = config or QWeatherConfig()
        if not self.config.api_key:
            raise WeatherAuthenticationError("QWEATHER_API_KEY is not configured")

        self._client = HttpClient(
            api_key=self.config.api_key,
            timeout_seconds=self.config.timeout_seconds,
            max_retries=self.config.max_retries,
            retry_backoff_seconds=self.config.retry_backoff_seconds,
        )

    def lookup_location(self, location: str, number: int = 10) -> list[GeoLocation]:
        payload = self._client.get(
            f"{self.config.geo_base_url}/v2/city/lookup",
            params={"location": location, "number": number, "lang": self.config.lang},
        )
        self._ensure_success(payload)

        locations = [GeoLocation.model_validate(item) for item in payload.get("location", [])]
        if not locations:
            raise LocationNotFoundError(f"No matching location found for: {location}")

        return locations

    def get_hourly_weather(
        self,
        location_id: str,
        hours: Literal["24h", "72h", "168h"] = "72h",
    ) -> HourlyWeatherResponse:
        payload = self._client.get(
            f"{self.config.weather_base_url}/v7/weather/{hours}",
            params={"location": location_id, "lang": self.config.lang},
        )
        self._ensure_success(payload)
        return HourlyWeatherResponse.model_validate(payload)

    def get_weather_warning(self, latitude: str, longitude: str) -> WeatherWarningResponse:
        payload = self._client.get(
            f"{self.config.warning_base_url}/v7/warning/now",
            params={"location": f"{longitude},{latitude}", "lang": self.config.lang},
        )
        self._ensure_success(payload)
        return WeatherWarningResponse.model_validate(payload)

    def close(self) -> None:
        self._client.close()

    @staticmethod
    def _ensure_success(payload: dict) -> None:
        if payload.get("code") == "200":
            return
        raise WeatherResponseError(f"Unexpected weather API response code: {payload.get('code')}")
