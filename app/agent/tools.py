from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.schemas import (
    CruiseEvaluateRequest,
    KnowledgeAccessContext,
    KnowledgeRetrievalRequest,
    MultiLocationComparisonRequest,
    RecommendationRequest,
)
from app.services.advice_retriever import retrieve_knowledge_by_request
from app.services.comparison import compare_locations
from app.services.conversation_query import get_user_conversation_detail, list_user_conversations
from app.services.cruise_evaluator import evaluate_cruise_request_with_artifacts
from app.services.recommendation_executor import build_recommendation_response
from app.services.risk_rule_explainer import explain_risk_rules


ToolSideEffect = Literal["read_only", "compute_only", "write", "external_call"]
ToolRiskLevel = Literal["low", "medium", "high"]
ToolUserScope = Literal["public", "current_user", "admin"]
ToolHandler = Callable[[dict[str, Any], "ToolExecutionContext"], Any]


class ToolRegistrationError(ValueError):
    pass


class ToolNotFoundError(KeyError):
    pass


@dataclass(frozen=True)
class ToolExecutionContext:
    user_id: str | None = None
    tenant_id: str | None = None
    role: str | None = None
    db: Session | None = None


class ToolSpec(BaseModel):
    name: str
    description: str
    side_effect: ToolSideEffect
    risk_level: ToolRiskLevel
    requires_auth: bool = True
    requires_admin: bool = False
    allowed_roles: list[str] = Field(default_factory=lambda: ["user", "admin"])
    user_scope: ToolUserScope = "current_user"
    timeout_ms: int = 30000
    input_schema_name: str | None = None
    output_schema_name: str | None = None


class ToolResult(BaseModel):
    success: bool
    tool_name: str
    data: Any = None
    error_code: str | None = None
    message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class RegisteredTool:
    spec: ToolSpec
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, spec: ToolSpec, handler: ToolHandler) -> None:
        if spec.name in self._tools:
            raise ToolRegistrationError(f"tool already registered: {spec.name}")
        self._tools[spec.name] = RegisteredTool(spec=spec, handler=handler)

    def get(self, name: str) -> RegisteredTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFoundError(f"tool not found: {name}") from exc

    def list_specs(self) -> list[ToolSpec]:
        return [item.spec for item in self._tools.values()]

    def call(
        self,
        name: str,
        payload: dict[str, Any] | None = None,
        *,
        context: ToolExecutionContext | None = None,
    ) -> ToolResult:
        try:
            tool = self.get(name)
        except ToolNotFoundError as exc:
            return ToolResult(success=False, tool_name=name, error_code="TOOL_NOT_FOUND", message=str(exc))

        safe_context = context or ToolExecutionContext()
        if tool.spec.requires_auth and not safe_context.user_id:
            return ToolResult(
                success=False,
                tool_name=name,
                error_code="AUTH_CONTEXT_REQUIRED",
                message="tool requires authenticated user context",
            )
        if tool.spec.requires_admin and safe_context.role != "admin":
            return ToolResult(
                success=False,
                tool_name=name,
                error_code="ADMIN_CONTEXT_REQUIRED",
                message="tool requires admin context",
            )

        try:
            data = tool.handler(payload or {}, safe_context)
        except ValidationError as exc:
            return ToolResult(
                success=False,
                tool_name=name,
                error_code="INVALID_TOOL_INPUT",
                message=str(exc),
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                tool_name=name,
                error_code=exc.__class__.__name__,
                message=str(exc),
            )

        return ToolResult(
            success=True,
            tool_name=name,
            data=_dump_tool_data(data),
            metadata={
                "side_effect": tool.spec.side_effect,
                "risk_level": tool.spec.risk_level,
                "allowed_roles": list(tool.spec.allowed_roles),
                "user_scope": tool.spec.user_scope,
            },
        )


def create_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="evaluate_flight_risk",
            description="Evaluate low-altitude drone flight risk for one location and time range.",
            side_effect="compute_only",
            risk_level="high",
            input_schema_name="CruiseEvaluateRequest",
            output_schema_name="CruiseAssessmentResponse",
        ),
        _evaluate_flight_risk,
    )
    registry.register(
        ToolSpec(
            name="recommend_flight_windows",
            description="Recommend available flight windows for a drone task.",
            side_effect="compute_only",
            risk_level="high",
            input_schema_name="RecommendationRequest",
            output_schema_name="RecommendationResponse",
        ),
        _recommend_flight_windows,
    )
    registry.register(
        ToolSpec(
            name="compare_flight_locations",
            description="Compare multiple candidate locations for a drone task.",
            side_effect="compute_only",
            risk_level="high",
            input_schema_name="MultiLocationComparisonRequest",
            output_schema_name="MultiLocationComparisonResponse",
        ),
        _compare_flight_locations,
    )
    registry.register(
        ToolSpec(
            name="retrieve_rag_advice",
            description="Retrieve RAG advice snippets with access and business metadata filters.",
            side_effect="read_only",
            risk_level="medium",
            input_schema_name="KnowledgeRetrievalRequest",
            output_schema_name="KnowledgeRetrievalResponse",
        ),
        _retrieve_rag_advice,
    )
    registry.register(
        ToolSpec(
            name="query_knowledge_snippets",
            description="Query knowledge snippets without running risk evaluation.",
            side_effect="read_only",
            risk_level="medium",
            input_schema_name="KnowledgeRetrievalRequest",
            output_schema_name="KnowledgeRetrievalResponse",
        ),
        _retrieve_rag_advice,
    )
    registry.register(
        ToolSpec(
            name="explain_risk_rules",
            description="Explain risk decision rules, thresholds, warning adjustments, and rule source.",
            side_effect="read_only",
            risk_level="low",
            requires_auth=False,
            user_scope="public",
        ),
        _explain_risk_rules,
    )
    registry.register(
        ToolSpec(
            name="query_user_history",
            description="Query current user's conversation history by list or detail mode.",
            side_effect="read_only",
            risk_level="low",
        ),
        _query_user_history,
    )
    return registry


def _evaluate_flight_risk(payload: dict[str, Any], context: ToolExecutionContext) -> Any:
    request = CruiseEvaluateRequest.model_validate(payload)
    return evaluate_cruise_request_with_artifacts(request).response


def _recommend_flight_windows(payload: dict[str, Any], context: ToolExecutionContext) -> Any:
    request = RecommendationRequest.model_validate(payload)
    return build_recommendation_response(request)


def _compare_flight_locations(payload: dict[str, Any], context: ToolExecutionContext) -> Any:
    request = MultiLocationComparisonRequest.model_validate(payload)
    return compare_locations(request)


def _retrieve_rag_advice(payload: dict[str, Any], context: ToolExecutionContext) -> Any:
    request = KnowledgeRetrievalRequest.model_validate(payload)
    access_context = KnowledgeAccessContext(user_id=context.user_id, tenant_id=context.tenant_id, role=context.role)
    return retrieve_knowledge_by_request(request, access_context=access_context)


def _explain_risk_rules(payload: dict[str, Any], context: ToolExecutionContext) -> Any:
    return explain_risk_rules(payload)


def _query_user_history(payload: dict[str, Any], context: ToolExecutionContext) -> Any:
    if context.db is not None:
        return _query_user_history_with_db(payload, context, db=context.db)

    with SessionLocal() as db:
        return _query_user_history_with_db(payload, context, db=db)


def _query_user_history_with_db(payload: dict[str, Any], context: ToolExecutionContext, *, db: Session) -> Any:

    mode = str(payload.get("mode") or "list")
    if mode == "detail":
        conversation_id = payload.get("conversation_id")
        if not conversation_id:
            raise ValueError("conversation_id is required for detail mode")
        return get_user_conversation_detail(
            db=db,
            user_id=str(context.user_id),
            conversation_id=str(conversation_id),
        )

    return list_user_conversations(
        db=db,
        user_id=str(context.user_id),
        page=int(payload.get("page") or 1),
        page_size=int(payload.get("page_size") or 20),
        keyword=payload.get("keyword"),
        session_id=payload.get("session_id"),
        intent=payload.get("intent"),
        parser_source=payload.get("parser_source"),
    )


def _dump_tool_data(data: Any) -> Any:
    if isinstance(data, BaseModel):
        return data.model_dump(mode="json")
    if data is None:
        return None
    return data


default_tool_registry = create_default_tool_registry()
