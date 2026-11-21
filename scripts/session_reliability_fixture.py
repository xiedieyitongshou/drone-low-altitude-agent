"""Isolated HTTP weather fixture; never imported by the application runtime."""

import json
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo


STATE = {"delay_seconds": 0.0, "calls": []}
LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send_json(self, value):
        data = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
        with LOCK:
            STATE.update({key: value for key, value in payload.items() if key in {"delay_seconds"}})
            if payload.get("clear"):
                STATE["calls"].clear()
        self.send_json({"ok": True})

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/control":
            with LOCK:
                self.send_json(dict(STATE))
            return
        with LOCK:
            STATE["calls"].append({"path": parsed.path, "at": time.time()})
            delay = STATE["delay_seconds"]
        time.sleep(delay)
        now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(minute=0, second=0, microsecond=0)
        if parsed.path.endswith("/lookup"):
            location = parse_qs(parsed.query).get("location", ["深圳"])[0]
            name = "广州" if "广州" in location else "深圳"
            self.send_json({"code": "200", "location": [{
                "id": "guangzhou" if name == "广州" else "shenzhen", "name": name,
                "lat": "23.13" if name == "广州" else "22.54", "lon": "113.26" if name == "广州" else "114.05",
            }]})
        elif parsed.path.endswith("/72h"):
            self.send_json({"code": "200", "updateTime": now.isoformat(), "hourly": [
                {"fxTime": (now + timedelta(hours=hour)).isoformat(), "temp": "20", "text": "晴",
                 "windSpeed": "5", "windScale": "1-2", "humidity": "50", "precip": "0", "pop": "0"}
                for hour in range(73)
            ]})
        else:
            self.send_json({"metadata": {"timestamp": now.isoformat()}, "alerts": []})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
