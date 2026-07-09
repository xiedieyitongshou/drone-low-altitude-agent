from pydantic import BaseModel, Field

from app.schemas.warning import WarningDataBundle
from app.schemas.weather import LocationInfo, WeatherDataBundle


class WeatherFetchResponse(BaseModel):
    success: bool = True
    message: str = "weather data fetched"
    request: dict[str, str | bool | None]
    location: dict[str, object]
    weather: dict[str, object]
    warnings: dict[str, object]
    standardized_location: LocationInfo
    standardized_weather: WeatherDataBundle
    standardized_warnings: WarningDataBundle
    sample_path: str | None = None


class WeatherFetchErrorContext(BaseModel):
    location: str
    date: str
    start_time: str
    end_time: str
    task_type: str
    purpose: str | None = None
