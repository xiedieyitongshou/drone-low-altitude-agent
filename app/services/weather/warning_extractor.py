from app.schemas.warning import WarningData, WarningDataBundle
from app.services.weather.schemas import WeatherWarning, WeatherWarningResponse


def extract_warnings(warning_response: WeatherWarningResponse) -> WarningDataBundle:
    warnings = [extract_warning_item(item) for item in warning_response.alerts]
    return WarningDataBundle(
        warnings=warnings,
        has_warning=len(warnings) > 0,
        warning_count=len(warnings),
    )


def extract_warning_item(item: WeatherWarning) -> WarningData:
    return WarningData(
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
