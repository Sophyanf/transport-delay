from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from transport_contracts import (
    HealthResponse,
    ModelInfo,
    PredictionRequest,
    PredictionResponse,
    ReloadRequest,
)
from transport_model_core import ModelManager

from transport_ml_service.service import PredictionService


class BatchPredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PredictionRequest] = Field(
        min_length=1,
        max_length=10_000,
    )


class BatchPredictionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PredictionResponse]


# Создаёт маршруты ML-service.
def create_ml_router(
    manager: ModelManager,
    service: PredictionService,
) -> APIRouter:
    router = APIRouter()
    create_ml_router_prediction_routes(router, service)
    create_ml_router_management_routes(router, manager)
    return router


# Добавляет endpoints прогнозирования.
def create_ml_router_prediction_routes(
    router: APIRouter,
    service: PredictionService,
) -> None:
    @router.post("/predict", response_model=PredictionResponse)
    def predict(request: PredictionRequest) -> PredictionResponse:
        try:
            return service.predict(request)
        except (RuntimeError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error

    @router.post(
        "/predict-batch",
        response_model=BatchPredictionResponse,
    )
    def predict_batch(
        request: BatchPredictionRequest,
    ) -> BatchPredictionResponse:
        try:
            items = service.predict_batch(request.items)
            return BatchPredictionResponse(items=items)
        except (RuntimeError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error


# Добавляет endpoints управления моделью.
def create_ml_router_management_routes(
    router: APIRouter,
    manager: ModelManager,
) -> None:
    @router.post("/reload", response_model=ModelInfo)
    def reload(request: ReloadRequest) -> ModelInfo:
        try:
            model = create_ml_router_reload(manager, request)
            return create_ml_router_model_info(manager, model)
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error

    @router.get("/model", response_model=ModelInfo)
    def model_info() -> ModelInfo:
        model = manager.current_model()
        return create_ml_router_model_info(manager, model)

    @router.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return create_ml_router_health(manager)


# Загружает явно указанную или активную модель.
def create_ml_router_reload(
    manager: ModelManager,
    request: ReloadRequest,
) -> object:
    if request.plugin is None or request.version is None:
        return manager.load_active()
    return manager.reload(request.plugin, request.version)


# Формирует информацию об активной модели.
def create_ml_router_model_info(
    manager: ModelManager,
    model: object,
) -> ModelInfo:
    manifest = manager.current_manifest()
    return ModelInfo(
        name=str(model.name),
        version=str(model.version),
        feature_set=manifest.feature_set,
        target_type=manifest.target_type,
        loaded=True,
        artifact_path=manifest.artifact,
        metadata=manifest.metadata,
    )


# Формирует состояние готовности ML-service.
def create_ml_router_health(
    manager: ModelManager,
) -> HealthResponse:
    if not manager.is_ready():
        return HealthResponse(
            status="not_ready",
            service="ml-service",
        )
    model = manager.current_model()
    return HealthResponse(
        status="ok",
        service="ml-service",
        active_model=model.name,
        active_version=model.version,
    )
