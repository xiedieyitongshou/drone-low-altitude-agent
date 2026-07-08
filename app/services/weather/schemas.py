from pydantic import BaseModel, ConfigDict, Field


class GeoLocation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    location_id: str = Field(alias="id")
    name: str
    latitude: str = Field(alias="lat")
    longitude: str = Field(alias="lon")
    adm1: str | None = None
    adm2: str | None = None
    country: str | None = None
    timezone: str | None = Field(default=None, alias="tz")
    utc_offset: str | None = Field(default=None, alias="utcOffset")
    location_type: str | None = Field(default=None, alias="type")
    rank: str | None = None


class HourlyWeather(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    forecast_time: str = Field(alias="fxTime")
    temp: str | None = None
    text: str | None = None
    wind_scale: str | None = Field(default=None, alias="windScale")
    wind_speed: str | None = Field(default=None, alias="windSpeed")
    humidity: str | None = None
    precip: str | None = None
    pop: str | None = None
    pressure: str | None = None
    cloud: str | None = None


class HourlyWeatherResponse(BaseModel):
    code: str
    update_time: str | None = Field(default=None, alias="updateTime")
    hourly: list[HourlyWeather]


class WeatherWarning(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    warning_id: str | None = Field(default=None, alias="id")
    sender: str | None = None
    publish_time: str | None = Field(default=None, alias="pubTime")
    title: str | None = None
    start_time: str | None = Field(default=None, alias="startTime")
    end_time: str | None = Field(default=None, alias="endTime")
    status: str | None = None
    level: str | None = None
    severity: str | None = None
    severity_color: str | None = Field(default=None, alias="severityColor")
    text: str | None = None
    event: str | None = None
    type_name: str | None = Field(default=None, alias="type")


class WeatherWarningResponse(BaseModel):
    code: str
    warning: list[WeatherWarning] = Field(default_factory=list)
