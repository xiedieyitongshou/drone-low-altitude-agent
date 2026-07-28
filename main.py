import logging
import os
from contextlib import suppress
from datetime import datetime

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import load_environment
from app.db.models import User
from app.dependencies import get_current_user, get_db
from app.dependencies.auth import require_admin_user
from app.schemas import (
    AdminConversationDetailResponse,
    AdminConversationListResponse,
    AdminTaskStatsResponse,
    AdminUserListResponse,
    AdminUserResponse,
    AdminUserRoleUpdateRequest,
    AdminUserStatusUpdateRequest,
    CruiseAssessmentResponse,
    CruiseEvaluateRequest,
    CruiseHistoryResponse,
    ConversationDetailResponse,
    ConversationListResponse,
    ErrorDetail,
    ErrorResponse,
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResponse,
    MultiLocationComparisonRequest,
    MultiLocationComparisonResponse,
    NaturalLanguageParseRequest,
    NaturalLanguageParseResponse,
    OrchestratorRequest,
    OrchestratorResponse,
    RecommendationRequest,
    RecommendationResponse,
    TokenResponse,
    UnifiedBusinessResponse,
    UserLoginRequest,
    UserProfileResponse,
    UserProfileUpdateRequest,
    UserRegisterRequest,
    UserResponse,
    WeatherFetchResponse,
)
from app.services.admin_conversation_audit import get_admin_conversation_detail, list_admin_conversations
from app.services.admin_stats import get_admin_task_stats
from app.services.admin_user_management import (
    AdminUserNotFoundError,
    LastActiveAdminError,
    list_admin_users,
    update_user_role,
    update_user_status,
)
from app.services.auth_service import create_access_token, hash_password, verify_password
from app.services.advice_retriever import retrieve_knowledge_by_request
from app.services.comparison import compare_locations
from app.services.conversation_query import get_user_conversation_detail, list_user_conversations
from app.services.cruise_evaluator import evaluate_cruise_request_with_artifacts
from app.services.history_persistence import persist_cruise_evaluation
from app.services.history_query import get_cruise_history
from app.services.nl_parser import NaturalLanguageParseError, parse_natural_language_request
from app.services.profile_memory import get_user_profile_response, update_user_profile
from app.services.recommendation_executor import build_recommendation_response
from app.services.response_composer import compose_history_response
from app.services.session_memory import build_session_context, session_memory_store
from app.services.task_orchestrator import orchestrate_task_query
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


def parse_csv_env(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseModel):
    app_name: str = os.getenv("APP_NAME", "drone-low-altitude-agent")
    app_env: str = os.getenv("APP_ENV", "local")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    cors_allowed_origins: list[str] = parse_csv_env(
        os.getenv(
            "CORS_ALLOWED_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        )
    )


def setup_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


settings = Settings()
setup_logging(settings.log_level)
logger = logging.getLogger(settings.app_name)

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
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


@app.exception_handler(NaturalLanguageParseError)
async def natural_language_parse_exception_handler(request: Request, exc: NaturalLanguageParseError) -> JSONResponse:
    payload = ErrorResponse(
        error_code="NATURAL_LANGUAGE_PARSE_ERROR",
        message=str(exc),
        details=[
            ErrorDetail(field=field, message="required information not detected").model_dump()
            for field in exc.missing_fields
        ],
    )
    return JSONResponse(status_code=422, content=payload.model_dump())


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


def to_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
    )


def parse_datetime_query(value: str | None, field_name: str) -> datetime | None:
    if value is None or not value.strip():
        return None

    try:
        return datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} must be an ISO datetime",
        ) from exc


@app.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(payload: UserRegisterRequest, db: Session = Depends(get_db)) -> UserResponse:
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="username cannot be blank")

    existing_user = db.scalar(select(User).where(User.username == username))
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already exists")

    user = User(
        username=username,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip() if payload.display_name else username,
        role="user",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return to_user_response(user)


@app.post("/auth/login", response_model=TokenResponse)
def login_user(payload: UserLoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    username = payload.username.strip()
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid username or password")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user is disabled")

    return TokenResponse(
        access_token=create_access_token(user.id),
        user=to_user_response(user),
    )


@app.get("/auth/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return to_user_response(current_user)


@app.get("/admin/users", response_model=AdminUserListResponse)
def admin_list_users(
    page: int = 1,
    page_size: int = 20,
    username: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
) -> AdminUserListResponse:
    _ = current_user
    if role is not None and role not in {"user", "admin"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="role must be user or admin")

    return list_admin_users(
        db=db,
        page=page,
        page_size=page_size,
        username=username,
        role=role,
        is_active=is_active,
    )


@app.patch("/admin/users/{user_id}/status", response_model=AdminUserResponse)
def admin_update_user_status(
    user_id: str,
    payload: AdminUserStatusUpdateRequest,
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
) -> AdminUserResponse:
    _ = current_user
    try:
        return update_user_status(db=db, user_id=user_id, is_active=payload.is_active)
    except AdminUserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LastActiveAdminError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@app.patch("/admin/users/{user_id}/role", response_model=AdminUserResponse)
def admin_update_user_role(
    user_id: str,
    payload: AdminUserRoleUpdateRequest,
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
) -> AdminUserResponse:
    _ = current_user
    try:
        return update_user_role(db=db, user_id=user_id, role=payload.role)
    except AdminUserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LastActiveAdminError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@app.get("/admin/stats/tasks", response_model=AdminTaskStatsResponse)
def admin_get_task_stats(
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
) -> AdminTaskStatsResponse:
    _ = current_user
    return get_admin_task_stats(db=db)


@app.get("/admin/conversations", response_model=AdminConversationListResponse)
def admin_list_conversations(
    page: int = 1,
    page_size: int = 20,
    user_id: str | None = None,
    session_id: str | None = None,
    intent: str | None = None,
    parser_source: str | None = None,
    success: bool | None = None,
    keyword: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
) -> AdminConversationListResponse:
    _ = current_user
    return list_admin_conversations(
        db=db,
        page=page,
        page_size=page_size,
        user_id=user_id,
        session_id=session_id,
        intent=intent,
        parser_source=parser_source,
        success=success,
        keyword=keyword,
        created_from=parse_datetime_query(created_from, "created_from"),
        created_to=parse_datetime_query(created_to, "created_to"),
    )


@app.get("/admin/conversations/{conversation_id}", response_model=AdminConversationDetailResponse)
def admin_get_conversation_detail(
    conversation_id: str,
    current_user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
) -> AdminConversationDetailResponse:
    _ = current_user
    detail = get_admin_conversation_detail(db=db, conversation_id=conversation_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
    return detail


@app.get("/users/me/profile", response_model=UserProfileResponse)
def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserProfileResponse:
    profile = get_user_profile_response(session=db, user_id=current_user.id)
    db.commit()
    return profile


@app.patch("/users/me/profile", response_model=UserProfileResponse)
def update_my_profile(
    payload: UserProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserProfileResponse:
    return update_user_profile(session=db, user_id=current_user.id, payload=payload)


@app.get("/agent/conversations", response_model=ConversationListResponse)
def list_conversations(
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    session_id: str | None = None,
    intent: str | None = None,
    parser_source: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationListResponse:
    return list_user_conversations(
        db=db,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        keyword=keyword,
        session_id=session_id,
        intent=intent,
        parser_source=parser_source,
    )


@app.get("/agent/conversations/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation_detail(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationDetailResponse:
    detail = get_user_conversation_detail(db=db, user_id=current_user.id, conversation_id=conversation_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
    return detail


@app.post("/knowledge/advice/retrieve", response_model=KnowledgeRetrievalResponse)
def retrieve_knowledge(payload: KnowledgeRetrievalRequest) -> KnowledgeRetrievalResponse:
    logger.info("Starting knowledge retrieval", extra={"task_type": payload.task_type, "top_k": payload.top_k})
    result = retrieve_knowledge_by_request(payload)
    logger.info("Knowledge retrieval completed", extra={"snippet_count": len(result.snippets), "advice_count": len(result.advice)})
    return result


@app.post("/nl/parse", response_model=NaturalLanguageParseResponse)
def parse_natural_language(payload: NaturalLanguageParseRequest) -> NaturalLanguageParseResponse:
    logger.info("Starting natural language parse")
    context = session_memory_store.get(payload.session_id) if payload.session_id else None
    result = parse_natural_language_request(payload.query, context=context)
    logger.info(
        "Natural language parse completed",
        extra={
            "intent": result.intent,
            "target_endpoint": result.target_endpoint,
            "session_id": payload.session_id,
            "context_used": result.context_used,
        },
    )
    if payload.session_id:
        session_memory_store.set(payload.session_id, build_session_context(result.intent, result.parsed))

    return NaturalLanguageParseResponse(
        session_id=payload.session_id,
        intent=result.intent,
        target_endpoint=result.target_endpoint,
        parser_source=result.parser_source,
        parsed=result.parsed,
        context_used=result.context_used,
        warnings=result.warnings,
    )


@app.post("/agent/query", response_model=OrchestratorResponse)
def orchestrate_task(
    payload: OrchestratorRequest,
    current_user: User = Depends(get_current_user),
) -> OrchestratorResponse:
    logger.info("Starting task orchestration")
    result = orchestrate_task_query(payload.query, session_id=payload.session_id, user_id=current_user.id)
    logger.info(
        "Task orchestration completed",
        extra={
            "intent": result.intent,
            "success": result.success,
            "target_endpoint": result.target_endpoint,
            "session_id": payload.session_id,
            "user_id": result.user_id,
            "conversation_id": result.conversation_id,
            "context_used": result.context_used,
        },
    )
    return result


@app.post("/cruise/evaluate", response_model=CruiseAssessmentResponse)
def evaluate_cruise(payload: CruiseEvaluateRequest) -> CruiseAssessmentResponse:
    logger.info(
        "Starting cruise evaluation",
        extra={
            "location": payload.location,
            "date": payload.normalized_date,
            "start_time": payload.normalized_start_time,
            "end_time": payload.normalized_end_time,
            "task_type": payload.task_type,
        },
    )

    artifacts = evaluate_cruise_request_with_artifacts(payload)
    result = artifacts.response
    request_id = persist_cruise_evaluation(payload=payload, artifacts=artifacts)
    result.request["request_id"] = request_id
    logger.info(
        "Cruise evaluation completed",
        extra={
            "request_id": request_id,
            "selected_hour_count": len(result.advice.hourly_assessment),
            "warning_count": result.warnings.warning_count if result.warnings else 0,
            "overall_decision": result.advice.overall_decision,
        },
    )
    return result


@app.get("/cruise/history/{request_id}", response_model=CruiseHistoryResponse)
def read_cruise_history(request_id: str) -> CruiseHistoryResponse:
    logger.info("Reading cruise history", extra={"request_id": request_id})
    result = get_cruise_history(request_id)
    logger.info(
        "Cruise history loaded",
        extra={
            "request_id": request_id,
            "hour_count": len(result.advice.hourly_assessment),
            "warning_count": result.warnings.warning_count if result.warnings else 0,
        },
    )
    return result


@app.get("/cruise/history/{request_id}/composed", response_model=UnifiedBusinessResponse)
def read_cruise_history_composed(request_id: str) -> UnifiedBusinessResponse:
    logger.info("Reading composed cruise history", extra={"request_id": request_id})
    result = get_cruise_history(request_id)
    return compose_history_response(result)


@app.post("/cruise/compare", response_model=MultiLocationComparisonResponse)
def compare_cruise_locations(payload: MultiLocationComparisonRequest) -> MultiLocationComparisonResponse:
    logger.info(
        "Starting location comparison",
        extra={
            "locations": payload.locations,
            "date": payload.date,
            "start_time": payload.start_time,
            "end_time": payload.end_time,
            "task_type": payload.task_type,
        },
    )
    result = compare_locations(payload)
    logger.info(
        "Location comparison completed",
        extra={
            "location_count": len(payload.locations),
            "recommended_location": result.recommended_location.location if result.recommended_location else None,
        },
    )
    return result


@app.post("/cruise/recommend", response_model=RecommendationResponse)
def recommend_execution_windows(payload: RecommendationRequest) -> RecommendationResponse:
    logger.info(
        "Starting recommendation scan",
        extra={
            "location": payload.location,
            "date": payload.date,
            "task_type": payload.task_type,
            "scan_hours": payload.scan_hours,
            "min_window_hours": payload.min_window_hours,
        },
    )

    result = build_recommendation_response(payload)
    logger.info(
        "Recommendation scan completed",
        extra={
            "scanned_hour_count": len(result.weather.hourly_weather) if result.weather else 0,
            "recommended_window_count": len(result.recommendation.recommended_windows),
        },
    )
    return result


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
