from datetime import datetime
from zoneinfo import ZoneInfo


APP_TIMEZONE = ZoneInfo("Asia/Shanghai")


def now_in_app_timezone() -> datetime:
    return datetime.now(APP_TIMEZONE).replace(tzinfo=None)
