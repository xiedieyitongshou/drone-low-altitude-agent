import logging
import os

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = os.getenv("APP_NAME", "drone-low-altitude-agent")
    app_env: str = os.getenv("APP_ENV", "local")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()


def setup_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


settings = Settings()
setup_logging(settings.log_level)
logger = logging.getLogger(settings.app_name)

app = FastAPI(title=settings.app_name)


@app.on_event("startup")
def on_startup() -> None:
    logger.info(
        "Application starting",
        extra={"app_env": settings.app_env, "app_port": settings.app_port},
    )


@app.get("/")
def read_root() -> dict[str, str]:
    return {
        "message": "drone-low-altitude-agent is running",
        "app_env": settings.app_env,
    }


@app.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
    }


def main() -> None:
    uvicorn.run("main:app", host="127.0.0.1", port=settings.app_port, reload=True)


if __name__ == "__main__":
    main()
