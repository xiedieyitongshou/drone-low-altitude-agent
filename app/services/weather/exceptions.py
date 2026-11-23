class WeatherServiceError(Exception):
    pass


class WeatherAuthenticationError(WeatherServiceError):
    pass


class WeatherRequestError(WeatherServiceError):
    pass


class WeatherResponseError(WeatherServiceError):
    pass


class WeatherDataError(WeatherResponseError):
    """The requested assessment cannot be supported by the returned weather."""

    def __init__(
        self, message: str, *, error_code: str = "WEATHER_DATA_INCOMPLETE",
        details: list[dict[str, str]] | None = None, retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.details = details or []
        self.retryable = retryable
        self.status_code = 422 if error_code == "WEATHER_FORECAST_OUT_OF_RANGE" else 502


WEATHER_DATA_ERROR_CODES = frozenset({
    "WEATHER_DATA_INCOMPLETE", "WEATHER_DATA_INVALID", "WEATHER_FORECAST_OUT_OF_RANGE",
})
WEATHER_FAILURE_CODES = WEATHER_DATA_ERROR_CODES | {
    "WeatherRequestError", "WeatherResponseError", "WeatherAuthenticationError",
}


class LocationNotFoundError(WeatherServiceError):
    pass
