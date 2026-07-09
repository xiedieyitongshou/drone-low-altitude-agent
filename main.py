import logging
import os
from contextlib import suppress

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import load_environment
from app.schemas import (
    CruiseEvaluateRequest,
    ErrorDetail,
    ErrorResponse,
    InputValidationPreviewResponse,
    WeatherFetchResponse,
)
from app.services.weather import (
    GeoLocation,
    HourlyWeatherResponse,
    LocationNotFoundError,
    QWeatherService,
    WeatherAuthenticationError,
    WeatherRequestError,
    WeatherResponseError,
    WeatherSampleStore,
    WeatherServiceError,
    WeatherWarningResponse,
    to_location_info,
    to_warning_data_bundle,
    to_weather_data_bundle,
)


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
sample_store = WeatherSampleStore()


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


@app.exception_handler(WeatherAuthenticationError)
async def weather_auth_exception_handler(request: Request, exc: WeatherAuthenticationError) -> JSONResponse:
    payload = ErrorResponse(
        error_code="WEATHER_AUTH_ERROR",
        message=str(exc),
    )
    return JSONResponse(status_code=500, content=payload.model_dump())


@app.exception_handler(LocationNotFoundError)
async def location_not_found_exception_handler(request: Request, exc: LocationNotFoundError) -> JSONResponse:
    payload = ErrorResponse(
        error_code="LOCATION_NOT_FOUND",
        message=str(exc),
    )
    return JSONResponse(status_code=404, content=payload.model_dump())


@app.exception_handler(WeatherRequestError)
@app.exception_handler(WeatherResponseError)
async def weather_request_exception_handler(request: Request, exc: WeatherServiceError) -> JSONResponse:
    payload = ErrorResponse(
        error_code="WEATHER_REQUEST_ERROR",
        message=str(exc),
    )
    return JSONResponse(status_code=502, content=payload.model_dump())


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


@app.post("/cruise/weather-fetch", response_model=WeatherFetchResponse)
def fetch_weather_data(payload: CruiseEvaluateRequest) -> WeatherFetchResponse:
    logger.info(
        "Starting weather fetch",
        extra={
            "location": payload.location,
            "date": payload.normalized_date,
            "start_time": payload.normalized_start_time,
            "end_time": payload.normalized_end_time,
        },
    )

    weather_service = QWeatherService()
    try:
        location_payload = weather_service.lookup_location_payload(payload.location, number=1)
        locations = [GeoLocation.model_validate(item) for item in location_payload.get("location", [])]
        if not locations:
            raise LocationNotFoundError(f"No matching location found for: {payload.location}")
        selected_location = locations[0]

        logger.info(
            "Location resolved",
            extra={
                "location": payload.location,
                "location_id": selected_location.location_id,
                "latitude": selected_location.latitude,
                "longitude": selected_location.longitude,
            },
        )

        hourly_payload = weather_service.get_hourly_weather_payload(selected_location.location_id, hours="72h")
        warning_payload = weather_service.get_weather_warning_payload(
            latitude=selected_location.latitude,
            longitude=selected_location.longitude,
        )
        hourly_response = HourlyWeatherResponse.model_validate(hourly_payload)
        warning_response = WeatherWarningResponse.model_validate(warning_payload)

        logger.info(
            "Weather fetch completed",
            extra={
                "location_id": selected_location.location_id,
                "hourly_count": len(hourly_payload.get("hourly", [])),
                "warning_count": len(warning_payload.get("alerts", [])),
            },
        )

        standardized_location = to_location_info(selected_location)
        standardized_weather = to_weather_data_bundle(selected_location, hourly_response)
        standardized_warnings = to_warning_data_bundle(warning_response)

        sample_path = sample_store.save(
            location=payload.location,
            payload={
                "request": payload.model_dump(),
                "location_payload": location_payload,
                "hourly_payload": hourly_payload,
                "warning_payload": warning_payload,
                "standardized_location": standardized_location.model_dump(),
                "standardized_weather": standardized_weather.model_dump(),
                "standardized_warnings": standardized_warnings.model_dump(),
            },
        )

        return WeatherFetchResponse(
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
            },
            location=location_payload,
            weather=hourly_payload,
            warnings=warning_payload,
            standardized_location=standardized_location,
            standardized_weather=standardized_weather,
            standardized_warnings=standardized_warnings,
            sample_path=sample_path,
        )
    finally:
        with suppress(Exception):
            weather_service.close()


def main() -> None:
    uvicorn.run("main:app", host="127.0.0.1", port=settings.app_port, reload=True)


if __name__ == "__main__":
    main()
