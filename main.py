import logging
import os

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import load_environment
from app.schemas import CruiseEvaluateRequest, ErrorDetail, ErrorResponse, InputValidationPreviewResponse


load_environment()


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
    logger.info("Application starting")


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    details = []
    for error in exc.errors():
        location = error.get("loc", [])
        field = ".".join(str(item) for item in location if item != "body") or None
        details.append(ErrorDetail(field=field, message=error.get("msg", "invalid input")).model_dump())

    payload = ErrorResponse(
        error_code="INVALID_REQUEST",
        message="request validation failed",
        details=details,
    )
    return JSONResponse(status_code=422, content=payload.model_dump())


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled application error")
    payload = ErrorResponse(
        error_code="INTERNAL_SERVER_ERROR",
        message="internal server error",
    )
    return JSONResponse(status_code=500, content=payload.model_dump())


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


@app.post("/cruise/evaluate", response_model=InputValidationPreviewResponse)
def evaluate_cruise_input(payload: CruiseEvaluateRequest) -> InputValidationPreviewResponse:
    return InputValidationPreviewResponse(
        request={
            "location": payload.location,
            "date": payload.normalized_date,
            "start_time": payload.normalized_start_time,
            "end_time": payload.normalized_end_time,
            "task_type": payload.task_type,
            "purpose": payload.purpose,
            "spans_next_day": payload.spans_next_day,
            "start_datetime": payload.start_datetime,
            "end_datetime": payload.end_datetime,
        }
    )


def main() -> None:
    uvicorn.run("main:app", host="127.0.0.1", port=settings.app_port, reload=True)


if __name__ == "__main__":
    main()
