from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import User
from app.schemas import (
    CruiseEvaluateRequest,
    KnowledgeAccessContext,
    KnowledgeRetrievalRequest,
    MissionTaskCreateRequest,
    MissionTaskRecommendRequest,
    MissionTaskSelectWindowRequest,
    MultiLocationComparisonRequest,
    RecommendationRequest,
)
from app.services.advice_retriever import retrieve_knowledge_by_request
from app.services.comparison import compare_locations
from app.services.conversation_query import get_user_conversation_detail, list_user_conversations
from app.services.cruise_evaluator import evaluate_cruise_request_with_artifacts
from app.services.history_persistence import persist_cruise_evaluation
from app.services.run_observability import current_observation, isolated_tool_observation, merge_tool_observation
from app.services.execution_budget import (
    ExecutionBudget, ExecutionCapacityError, ExecutionTimeout, check_execution_budget,
    current_budget, execution_pool, worker_database, worker_database_bind,
)
from app.services.weather.exceptions import WeatherDataError
from app.services.mission_task_management import create_mission_task
from app.services.mission_task_versioning import MissionTaskVersionConflictError
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
    task_version: int | None = None
    has_recommended_windows: bool = False
    budget: ExecutionBudget | None = None


class ToolSpec(BaseModel):
    name: str
    description: str
    side_effect: ToolSideEffect
    risk_level: ToolRiskLevel
    requires_auth: bool = True
    requires_admin: bool = False
    allowed_roles: list[str] = Field(default_factory=lambda: ["user", "admin"])
    user_scope: ToolUserScope = "current_user"
    timeout_ms: int = Field(default=30000, gt=0)
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

        parent_budget = current_budget() or safe_context.budget
        budget = ExecutionBudget.start(tool.spec.timeout_ms, parent=parent_budget,
                                       error_code="TOOL_TIMEOUT")
        if safe_context.budget is not None:
            budget.deadline = min(budget.deadline, safe_context.budget.deadline)
        execution_payload = deepcopy(payload or {})
        try:
            database_bind = worker_database_bind(safe_context.db)
        except ValueError as exc:
            return ToolResult(success=False, tool_name=name, error_code="INVALID_TOOL_INPUT", message=str(exc))
        worker_context = replace(safe_context, db=None, budget=budget)

        def invoke():
            with worker_database(database_bind) as owned_db, isolated_tool_observation() as observation:
                execution_context = replace(worker_context, db=owned_db)
                try:
                    data = tool.handler(execution_payload, execution_context)
                    budget.check()
                    return _dump_tool_data(data), observation, None
                except BaseException as exc:
                    return None, observation, exc

        try:
            if safe_context.budget is not None:
                safe_context.budget.check()
            data, observation, error = execution_pool("tool").run(invoke, budget)
            merge_tool_observation(observation)
            if error is not None:
                raise error
        except (ExecutionTimeout, ExecutionCapacityError) as exc:
            return ToolResult(
                success=False, tool_name=name, error_code=exc.error_code, message=str(exc),
                metadata={"retryable": True, "timeout_ms": tool.spec.timeout_ms,
                          "operation_may_have_committed": tool.spec.side_effect == "write",
                          "retry_with_same_operation_id": True},
            )
        except WeatherDataError as exc:
            return ToolResult(
                success=False, tool_name=name, error_code=exc.error_code, message=str(exc),
                metadata={"weather_data": {"details": exc.details}, "retryable": exc.retryable},
            )
        except MissionTaskVersionConflictError as exc:
            return ToolResult(success=False, tool_name=name, error_code=exc.error_code, message=str(exc))
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
            side_effect="write",
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
    registry.register(
        ToolSpec(
            name="create_mission_task",
            description="Create a low-altitude mission task for the current user.",
            side_effect="write",
            risk_level="medium",
            input_schema_name="MissionTaskCreateToolInput",
            output_schema_name="MissionTaskResponse",
        ),
        _create_mission_task,
    )
    registry.register(
        ToolSpec(
            name="evaluate_mission_task",
            description="Evaluate weather and rule risk for an existing mission task.",
            side_effect="write",
            risk_level="high",
            input_schema_name="MissionTaskActionToolInput",
            output_schema_name="CruiseAssessmentResponse",
        ),
        _evaluate_mission_task,
    )
    registry.register(
        ToolSpec(
            name="recommend_mission_task_windows",
            description="Recommend candidate execution windows for an existing mission task.",
            side_effect="write",
            risk_level="high",
            input_schema_name="MissionTaskRecommendToolInput",
            output_schema_name="RecommendationResponse",
        ),
        _recommend_mission_task_windows,
    )
    registry.register(
        ToolSpec(
            name="select_mission_task_window",
            description="Select one recommended execution window for an existing mission task.",
            side_effect="write",
            risk_level="high",
            input_schema_name="MissionTaskSelectWindowToolInput",
            output_schema_name="MissionTaskResponse",
        ),
        _select_mission_task_window,
    )
    registry.register(
        ToolSpec(
            name="preflight_check_mission_task",
            description="Recheck an existing mission task before execution with fresh weather and rules.",
            side_effect="write",
            risk_level="high",
            input_schema_name="MissionTaskActionToolInput",
            output_schema_name="CruiseAssessmentResponse",
        ),
        _preflight_check_mission_task,
    )
    return registry


def _evaluate_flight_risk(payload: dict[str, Any], context: ToolExecutionContext) -> Any:
    request = CruiseEvaluateRequest.model_validate(payload)
    artifacts = evaluate_cruise_request_with_artifacts(request)
    response = artifacts.response
    observation = current_observation()
    if observation:
        response.request["trace_id"] = observation.trace_id
    try:
        request_id = persist_cruise_evaluation(payload=request, artifacts=artifacts, user_id=context.user_id, db=context.db)
        response.request.update(request_id=request_id, persistence_status="saved")
    except Exception as exc:
        # A failed history write must not replay weather calls or replace a computed decision.
        response.request.update(persistence_status="failed", persistence_error=type(exc).__name__)
        if observation:
            observation.emit("error", error_code="ASSESSMENT_SAVE_FAILED", metadata={"error_type": type(exc).__name__})
    return response


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


def _create_mission_task(payload: dict[str, Any], context: ToolExecutionContext) -> Any:
    from app.services.idempotency import AGENT_TASK_CREATE, current_agent_operation_id

    def call(db: Session) -> Any:
        current_user = _get_current_tool_user(db, context)
        request_payload = {
            "title": payload.get("title") or payload.get("task_title"),
            "purpose": payload.get("purpose"),
            "location": payload.get("location"),
            "date": payload.get("date"),
            "start_time": payload.get("start_time"),
            "end_time": payload.get("end_time"),
            "task_type": payload.get("task_type"),
            "candidate_locations": payload.get("candidate_locations") or [],
            "profile_context": payload.get("profile_context") or {},
            "metadata": payload.get("metadata") or {},
        }
        request = MissionTaskCreateRequest.model_validate(request_payload)
        return create_mission_task(
            db=db, current_user=current_user, payload=request,
            idempotency_key=current_agent_operation_id(), operation=AGENT_TASK_CREATE,
        )

    return _with_tool_db(context, call)


def _evaluate_mission_task(payload: dict[str, Any], context: ToolExecutionContext) -> Any:
    from app.services.mission_task_execution import evaluate_mission_task

    return _call_task_action(payload, context, evaluate_mission_task)


def _recommend_mission_task_windows(payload: dict[str, Any], context: ToolExecutionContext) -> Any:
    from app.services.mission_task_execution import recommend_mission_task_windows

    def call(db: Session) -> Any:
        current_user = _get_current_tool_user(db, context)
        task_id = _require_task_id(payload)
        request = MissionTaskRecommendRequest.model_validate(
            {
                "expected_version": _task_operation_version(db, current_user, context, payload, "recommend_task"),
                "scan_hours": payload.get("scan_hours") or 72,
                "min_window_hours": payload.get("min_window_hours") or 2,
            }
        )
        return recommend_mission_task_windows(db=db, current_user=current_user, task_id=task_id, payload=request)

    return _with_tool_db(context, call)


def _select_mission_task_window(payload: dict[str, Any], context: ToolExecutionContext) -> Any:
    from app.services.mission_task_execution import select_mission_task_window

    def call(db: Session) -> Any:
        current_user = _get_current_tool_user(db, context)
        task_id = _require_task_id(payload)
        request = MissionTaskSelectWindowRequest.model_validate(
            {
                "expected_version": _task_operation_version(db, current_user, context, payload, "select_task_window"),
                "rank": payload.get("rank") or payload.get("window_rank"),
                "window": payload.get("window"),
            }
        )
        return select_mission_task_window(db=db, current_user=current_user, task_id=task_id, payload=request)

    return _with_tool_db(context, call)


def _preflight_check_mission_task(payload: dict[str, Any], context: ToolExecutionContext) -> Any:
    from app.services.mission_task_execution import preflight_check_mission_task

    return _call_task_action(payload, context, preflight_check_mission_task)


def _call_task_action(payload: dict[str, Any], context: ToolExecutionContext, handler: Callable[..., Any]) -> Any:
    def call(db: Session) -> Any:
        current_user = _get_current_tool_user(db, context)
        version = _task_operation_version(db, current_user, context, payload, handler.__name__)
        return handler(db=db, current_user=current_user, task_id=_require_task_id(payload), expected_version=version)

    return _with_tool_db(context, call)


def _task_operation_version(db: Session, user: User, context: ToolExecutionContext, payload: dict, action: str) -> int:
    from app.services.idempotency import bind_agent_task_version
    from app.db.models import MissionTask
    from app.services.mission_task_management import MissionTaskNotFoundError, MissionTaskPermissionError, _ensure_not_terminal
    from app.services.mission_task_versioning import check_task_version

    task_id = _require_task_id(payload)
    task = db.get(MissionTask, task_id, populate_existing=True)
    if task is None:
        raise MissionTaskNotFoundError("mission task not found")
    if task.user_id != user.id:
        raise MissionTaskPermissionError("cannot operate another user's mission task")
    if action == "select_task_window" and (context.task_version is None or not context.has_recommended_windows):
        raise MissionTaskVersionConflictError("当前会话缺少推荐结果的任务版本，请重新推荐窗口。")
    version = context.task_version if context.task_version is not None else task.version
    version = bind_agent_task_version(db=db, user_id=user.id, task_id=task_id, action=action, version=version)
    check_task_version(task, version)
    _ensure_not_terminal(task)
    return version


def _with_tool_db(context: ToolExecutionContext, callback: Callable[[Session], Any]) -> Any:
    check_execution_budget()
    if context.db is not None:
        return callback(context.db)

    with SessionLocal() as db:
        return callback(db)


def _get_current_tool_user(db: Session, context: ToolExecutionContext) -> User:
    if not context.user_id:
        raise PermissionError("authenticated user context is required")
    user = db.get(User, str(context.user_id))
    if user is None or not user.is_active:
        raise PermissionError("authenticated user is not available")
    return user


def _require_task_id(payload: dict[str, Any]) -> str:
    task_id = payload.get("task_id")
    if not task_id:
        raise ValueError("task_id is required")
    return str(task_id)


def _dump_tool_data(data: Any) -> Any:
    if isinstance(data, BaseModel):
        return data.model_dump(mode="json")
    if data is None:
        return None
    return data


default_tool_registry = create_default_tool_registry()
