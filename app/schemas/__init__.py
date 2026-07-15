from app.schemas.assessment import (
    CruiseAssessmentAdvice,
    CruiseHistoryResponse,
    CruiseAssessmentResponse,
    HourlyAssessment,
    InputValidationPreviewResponse,
    RiskDecision,
)
from app.schemas.comparison import ComparedLocationResult, MultiLocationComparisonRequest, MultiLocationComparisonResponse
from app.schemas.error import ErrorDetail, ErrorResponse
from app.schemas.fetch import WeatherFetchErrorContext, WeatherFetchResponse
from app.schemas.recommendation import (
    RecommendationRequest,
    RecommendationResponse,
    RecommendationResult,
    RecommendationStrategy,
    RecommendationWindow,
)
from app.schemas.request import CruiseEvaluateRequest
from app.schemas.warning import WarningData, WarningDataBundle
from app.schemas.weather import LocationInfo, WeatherDataBundle, WeatherHourData

__all__ = [
    "CruiseAssessmentAdvice",
    "CruiseHistoryResponse",
    "CruiseAssessmentResponse",
    "CruiseEvaluateRequest",
    "ComparedLocationResult",
    "ErrorDetail",
    "ErrorResponse",
    "WeatherFetchErrorContext",
    "WeatherFetchResponse",
    "HourlyAssessment",
    "InputValidationPreviewResponse",
    "LocationInfo",
    "MultiLocationComparisonRequest",
    "MultiLocationComparisonResponse",
    "RecommendationRequest",
    "RecommendationResponse",
    "RecommendationResult",
    "RecommendationStrategy",
    "RecommendationWindow",
    "RiskDecision",
    "WarningData",
    "WarningDataBundle",
    "WeatherDataBundle",
    "WeatherHourData",
]
