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


class WeatherWarningMetadata(BaseModel):
    tag: str | None = None
    zero_result: bool | None = Field(default=None, alias="zeroResult")
    attributions: list[str] = Field(default_factory=list)


class WeatherWarningSenderName(BaseModel):
    code: str | None = None
    name: str | None = None


class WeatherWarningMessageType(BaseModel):
    code: str | None = None
    supersedes: list[str] = Field(default_factory=list)


class WeatherWarningEventType(BaseModel):
    name: str | None = None
    code: str | None = None


class WeatherWarningColor(BaseModel):
    code: str | None = None
    red: int | None = None
    green: int | None = None
    blue: int | None = None
    alpha: int | None = None


class WeatherWarning(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    warning_id: str | None = Field(default=None, alias="id")
    sender_name: str | None = Field(default=None, alias="senderName")
    issued_time: str | None = Field(default=None, alias="issuedTime")
    message_type: WeatherWarningMessageType | None = Field(default=None, alias="messageType")
    event_type: WeatherWarningEventType | None = Field(default=None, alias="eventType")
    urgency: str | None = None
    severity: str | None = None
    certainty: str | None = None
    icon: str | None = None
    color: WeatherWarningColor | None = None
    effective_time: str | None = Field(default=None, alias="effectiveTime")
    onset_time: str | None = Field(default=None, alias="onsetTime")
    expire_time: str | None = Field(default=None, alias="expireTime")
    headline: str | None = None
    description: str | None = None
    criteria: str | None = None
    response_types: list[str] = Field(default_factory=list, alias="responseTypes")
    instruction: str | None = None


class WeatherWarningResponse(BaseModel):
    metadata: WeatherWarningMetadata
    alerts: list[WeatherWarning] = Field(default_factory=list)
