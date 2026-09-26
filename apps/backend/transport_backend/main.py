import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from redis.asyncio import Redis

from transport_backend.alerts import AlertService
from transport_backend.api import create_backend_router
from transport_backend.consumer import PredictionConsumer
from transport_backend.repositories import IncidentRepository
from transport_backend.settings import BackendSettings
from transport_backend.websocket import WebSocketHub


class BackendContainer:
    # Создаёт зависимости Backend-приложения.
    def __init__(self, settings: BackendSettings) -> None:
        self.settings = settings
        self.redis = Redis.from_url(
            settings.redis_url,
            decode_responses=False,
        )
        self.repository = IncidentRepository(
            redis=self.redis,
            key_prefix=settings.incident_prefix,
            retention_s=settings.incident_retention_s,
            index_limit=settings.incident_index_limit,
        )
        self.websocket_hub = WebSocketHub()
        self.consumer = self._create_consumer()

    # Создаёт потребителя прогнозов.
    def _create_consumer(self) -> PredictionConsumer:
        return PredictionConsumer(
            redis=self.redis,
            stream=self.settings.prediction_stream,
            group=self.settings.backend_prediction_group,
            consumer=self.settings.backend_prediction_consumer,
            repository=self.repository,
            alerts=AlertService(),
            websocket_hub=self.websocket_hub,
            read_count=self.settings.backend_stream_read_count,
            block_ms=self.settings.backend_stream_block_ms,
        )


settings = BackendSettings()
container = BackendContainer(settings)


# Управляет жизненным циклом потребителя прогнозов.
@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await container.redis.ping()
    consumer_task = asyncio.create_task(container.consumer.run())
    try:
        yield
    finally:
        consumer_task.cancel()
        with suppress(Exception):
            await asyncio.gather(
                consumer_task,
                return_exceptions=True,
            )
        await container.redis.aclose()


# Создаёт FastAPI-приложение Backend.
def create_application() -> FastAPI:
    application = FastAPI(
        title="Transport Delay Backend",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.include_router(
        create_backend_router(
            container.repository,
            container.websocket_hub,
        ),
        prefix="/api/v1",
    )
    return application


logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = create_application()
