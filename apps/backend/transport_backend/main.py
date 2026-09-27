import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from transport_backend.alerts import AlertService
from transport_backend.api import create_backend_router
from transport_backend.consumer import PredictionConsumer
from transport_backend.repositories import (
    IncidentRepository,
    ScheduleContextRepository,
    VehicleRepository,
)
from transport_backend.score import ScoreService
from transport_backend.settings import BackendSettings
from transport_backend.submission import SubmissionService
from transport_backend.what_if import create_what_if_router
from transport_backend.websocket import WebSocketHub


class BackendContainer:
    # Создаёт зависимости Backend.
    def __init__(self, settings: BackendSettings) -> None:
        self.settings = settings
        self.redis = Redis.from_url(settings.redis_url)
        self.incidents = self._create_incidents()
        self.vehicles = self._create_vehicles()
        self.schedules = ScheduleContextRepository(settings.schedule_path)
        self.scores = self._create_scores()
        self.submissions = self._create_submissions()
        self.hub = WebSocketHub()
        self.consumer = self._create_consumer()

    # Создаёт репозиторий инцидентов.
    def _create_incidents(self) -> IncidentRepository:
        return IncidentRepository(
            self.redis,
            self.settings.incident_prefix,
            self.settings.incident_retention_s,
            self.settings.incident_index_limit,
        )

    # Создаёт репозиторий транспорта.
    def _create_vehicles(self) -> VehicleRepository:
        return VehicleRepository(
            self.redis,
            self.settings.vehicle_state_prefix,
            self.settings.telemetry_fresh_s,
            self.settings.telemetry_stale_s,
        )

    # Создаёт сервис проверки CSV.
    def _create_scores(self) -> ScoreService:
        return ScoreService(
            self.redis,
            self.settings.score_points_path,
            self.settings.score_ground_truth_path,
            self.settings.score_history_key,
            self.settings.score_history_limit,
            self.settings.mae_target,
        )

    # Создаёт сервис выгрузки submission.
    def _create_submissions(self) -> SubmissionService:
        return SubmissionService(
            self.settings.validate_points_path,
            self.settings.validate_predictions_path,
            self.settings.submission_path,
        )

    # Создаёт потребителя прогнозов.
    def _create_consumer(self) -> PredictionConsumer:
        return PredictionConsumer(
            self.redis,
            self.settings.prediction_stream,
            self.settings.backend_prediction_group,
            self.settings.backend_prediction_consumer,
            self.incidents,
            AlertService(),
            self.hub,
            self.settings.backend_stream_read_count,
            self.settings.backend_stream_block_ms,
        )


settings = BackendSettings()
container = BackendContainer(settings)


# Управляет фоновым потребителем прогнозов.
@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await container.redis.ping()
    task = asyncio.create_task(container.consumer.run())
    yield
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    await container.redis.aclose()


# Создаёт FastAPI-приложение.
def create_application() -> FastAPI:
    application = FastAPI(
        title="Transport Delay Backend",
        version="2.0.0",
        lifespan=lifespan,
    )
    router = create_backend_router(
        container.incidents,
        container.vehicles,
        container.schedules,
        container.scores,
        container.submissions,
        container.hub,
    )
    what_if_router = create_what_if_router(container.redis)
    application.include_router(router, prefix="/api")
    application.include_router(router, prefix="/api/v1")
    application.include_router(what_if_router, prefix="/api")
    application.include_router(what_if_router, prefix="/api/v1")
    return application


logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = create_application()
