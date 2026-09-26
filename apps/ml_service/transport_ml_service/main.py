from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from transport_model_core import ModelLoader, ModelManager

from transport_ml_service.api import create_ml_router
from transport_ml_service.service import PredictionService
from transport_ml_service.settings import MlServiceSettings

settings = MlServiceSettings()
loader = ModelLoader(settings.model_root)
manager = ModelManager(loader, settings.active_model_config)
prediction_service = PredictionService(manager)


# Загружает активную модель при старте сервиса.
@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    manager.load_active()
    yield


# Создаёт FastAPI-приложение ML-service.
def create_application() -> FastAPI:
    application = FastAPI(
        title="Transport Delay ML Service",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.include_router(
        create_ml_router(manager, prediction_service),
        prefix="/api/v1",
    )
    return application


app = create_application()
