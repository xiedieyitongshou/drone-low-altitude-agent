import json
from datetime import datetime
from pathlib import Path
from typing import Any


class WeatherSampleStore:
    def __init__(self, base_dir: str = "data/samples") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        location: str,
        payload: dict[str, Any],
    ) -> str:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_location = "".join(char if char.isalnum() else "_" for char in location).strip("_") or "location"
        file_path = self.base_dir / f"{timestamp}-{safe_location}.json"
        file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(file_path)
