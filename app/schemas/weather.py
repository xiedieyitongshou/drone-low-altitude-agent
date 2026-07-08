from pydantic import BaseModel, ConfigDict, Field


class LocationInfo(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    location_id: str
    name: str
    latitude: str
    longitude: str
    adm1: str | None = None
    adm2: str | None = None
    country: str | None = None
    timezone: str | None = None
    utc_offset: str | None = None


class WeatherHourData(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    fx_time: str = Field(..., description="逐小时天气时间")
    temp: str | None = None
    text: str | None = None
    wind_scale: str | None = None
    wind_speed: str | None = None
    humidity: str | None = None
    precip: str | None = None
    pop: str | None = None
    pressure: str | None = None
    cloud: str | None = None


class WeatherDataBundle(BaseModel):
    location: LocationInfo
    update_time: str | None = None
    hourly_weather: list[WeatherHourData]
