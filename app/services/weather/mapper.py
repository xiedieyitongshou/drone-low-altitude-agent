from app.schemas.warning import WarningData, WarningDataBundle
from app.schemas.weather import LocationInfo, WeatherDataBundle, WeatherHourData
from app.services.weather.schemas import GeoLocation, HourlyWeatherResponse, WeatherWarningResponse


def to_location_info(location: GeoLocation) -> LocationInfo:
    return LocationInfo(
        location_id=location.location_id,
        name=location.name,
        latitude=location.latitude,
        longitude=location.longitude,
        adm1=location.adm1,
        adm2=location.adm2,
        country=location.country,
        timezone=location.timezone,
        utc_offset=location.utc_offset,
    )


def to_weather_data_bundle(location: GeoLocation, weather_response: HourlyWeatherResponse) -> WeatherDataBundle:
    return WeatherDataBundle(
        location=to_location_info(location),
        update_time=weather_response.update_time,
        hourly_weather=[
            WeatherHourData(
                fx_time=item.forecast_time,
                temp=item.temp,
                text=item.text,
                wind_scale=item.wind_scale,
                wind_speed=item.wind_speed,
                humidity=item.humidity,
                precip=item.precip,
                pop=item.pop,
                pressure=item.pressure,
                cloud=item.cloud,
            )
            for item in weather_response.hourly
        ],
    )


def to_warning_data_bundle(warning_response: WeatherWarningResponse) -> WarningDataBundle:
    warnings = [
        WarningData(
            warning_id=item.warning_id,
            event_type=item.event_type.name if item.event_type else None,
            warning_level=item.severity,
            title=item.headline,
            sender=item.sender_name,
            publish_time=item.issued_time,
            start_time=item.effective_time,
            end_time=item.expire_time,
            status=item.message_type.code if item.message_type else None,
            text=item.description,
        )
        for item in warning_response.alerts
    ]
    return WarningDataBundle(
        warnings=warnings,
        has_warning=len(warnings) > 0,
        warning_count=len(warnings),
    )
