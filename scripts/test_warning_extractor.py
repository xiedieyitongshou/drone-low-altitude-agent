from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.weather import extract_warnings
from app.services.weather.schemas import WeatherWarningResponse


def main() -> None:
    response_with_warning = WeatherWarningResponse.model_validate(
        {
            "metadata": {
                "tag": "sample",
                "zeroResult": False,
                "attributions": ["QWeather"],
            },
            "alerts": [
                {
                    "id": "warning-1",
                    "senderName": "深圳气象台",
                    "issuedTime": "2026-07-12T08:00Z",
                    "messageType": {"code": "alert", "supersedes": []},
                    "eventType": {"name": "雷电预警", "code": "2010"},
                    "severity": "orange",
                    "effectiveTime": "2026-07-12T08:00Z",
                    "expireTime": "2026-07-12T12:00Z",
                    "headline": "深圳雷电橙色预警",
                    "description": "未来数小时可能发生雷电活动",
                    "responseTypes": [],
                }
            ],
        }
    )

    response_without_warning = WeatherWarningResponse.model_validate(
        {
            "metadata": {
                "tag": "sample-empty",
                "zeroResult": True,
                "attributions": ["QWeather"],
            },
            "alerts": [],
        }
    )

    result_with_warning = extract_warnings(response_with_warning)
    result_without_warning = extract_warnings(response_without_warning)

    print("with_warning_count:", result_with_warning.warning_count)
    print("with_warning_event:", result_with_warning.warnings[0].event_type)
    print("without_warning_count:", result_without_warning.warning_count)
    print("without_warning_has_warning:", result_without_warning.has_warning)


if __name__ == "__main__":
    main()
