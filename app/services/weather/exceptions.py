class WeatherServiceError(Exception):
    pass


class WeatherAuthenticationError(WeatherServiceError):
    pass


class WeatherRequestError(WeatherServiceError):
    pass


class WeatherResponseError(WeatherServiceError):
    pass


class LocationNotFoundError(WeatherServiceError):
    pass
