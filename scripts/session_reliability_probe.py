"""Linux-side HTTP probe controlled through JSON stdin by the Docker test runner."""

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import httpx


def request(item, barrier=None):
    if barrier:
        barrier.wait(timeout=10)
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=45, trust_env=False) as client:
            response = client.request(
                item.get("method", "GET"), item["url"], json=item.get("json"),
                headers={"Authorization": f"Bearer {item['token']}"} if item.get("token") else None,
            )
        try:
            body = response.json()
        except ValueError:
            body = {"text": response.text[:300]}
        return {"status": response.status_code, "body": body, "latency_ms": round((time.perf_counter() - started) * 1000, 3)}
    except httpx.HTTPError as exc:
        return {"status": 0, "body": {"error_type": type(exc).__name__}, "latency_ms": round((time.perf_counter() - started) * 1000, 3)}


def main():
    command = json.load(sys.stdin)
    if command.get("parallel"):
        items = command["requests"]
        barrier = Barrier(len(items))
        with ThreadPoolExecutor(max_workers=len(items)) as executor:
            result = list(executor.map(lambda item: request(item, barrier), items))
    else:
        result = [request(item) for item in command["requests"]]
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
