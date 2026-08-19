from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.weather import extract_warnings
from app.services.weather.schemas import WeatherWarningResponse


class WarningExtractorTestCase(unittest.TestCase):
    def test_extract_warning_fields(self) -> None:
        response = WeatherWarningResponse.model_validate(
            {
                "metadata": {"tag": "sample", "zeroResult": False, "attributions": ["QWeather"]},
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

        result = extract_warnings(response)

        self.assertTrue(result.has_warning)
        self.assertEqual(result.warning_count, 1)
        self.assertEqual(result.warnings[0].event_type, "雷电预警")
        self.assertEqual(result.warnings[0].warning_level, "orange")
        self.assertEqual(result.warnings[0].status, "alert")

    def test_empty_warning_response_is_supported(self) -> None:
        response = WeatherWarningResponse.model_validate(
            {
                "metadata": {"tag": "empty", "zeroResult": True, "attributions": ["QWeather"]},
                "alerts": [],
            }
        )

        result = extract_warnings(response)

        self.assertFalse(result.has_warning)
        self.assertEqual(result.warning_count, 0)
        self.assertEqual(result.warnings, [])


if __name__ == "__main__":
    unittest.main()
