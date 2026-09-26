import asyncio
import logging
from contextlib import suppress

from redis.asyncio import Redis

from transport_feature_worker.consumer import TelemetryConsumer
from transport_feature_worker.predictor import PredictionPublisher
from transport_feature_worker.scheduler import (
    CurrentDeviationRepository,
    PredictionScheduler,
    ScheduleRepository,
)
from transport_feature_worker.settings import FeatureWorkerSettings
from transport_feature_worker.state import VehicleStateRepository


# Периодически запускает генерацию прогнозных точек.
async def run_scheduler_loop(
    scheduler: PredictionScheduler,
    period_s: float,
) -> None:
    while True:
        try:
            await scheduler.run_once()
        except Exception:
            logging.getLogger(__name__).exception("Scheduler iteration failed")
        await asyncio.sleep(period_s)


# Создаёт компоненты Feature Worker.
def create_feature_worker(
    settings: FeatureWorkerSettings,
    redis: Redis,
) -> tuple[TelemetryConsumer, PredictionScheduler]:
    state = VehicleStateRepository(
        redis,
        settings.vehicle_state_prefix,
        settings.vehicle_state_retention_s,
    )
    schedules = ScheduleRepository(settings.schedule_path)
    deviations = CurrentDeviationRepository(
        redis,
        settings.current_deviation_prefix,
    )
    predictor = PredictionPublisher(
        redis=redis,
        ml_service_url=settings.ml_service_url,
        prediction_stream=settings.prediction_stream,
        prediction_stream_maxlen=settings.prediction_stream_maxlen,
        timeout_s=settings.ml_request_timeout_s,
    )
    consumer = create_feature_worker_consumer(
        settings,
        redis,
        state,
    )
    scheduler = create_feature_worker_scheduler(
        settings,
        redis,
        state,
        schedules,
        deviations,
        predictor,
    )
    return consumer, scheduler


# Создаёт потребителя телеметрии.
def create_feature_worker_consumer(
    settings: FeatureWorkerSettings,
    redis: Redis,
    state: VehicleStateRepository,
) -> TelemetryConsumer:
    return TelemetryConsumer(
        redis=redis,
        stream=settings.telemetry_stream,
        group=settings.feature_worker_group,
        consumer=settings.feature_worker_consumer,
        state=state,
        read_count=settings.stream_read_count,
        block_ms=settings.stream_block_ms,
    )


# Создаёт планировщик прогнозов.
def create_feature_worker_scheduler(
    settings: FeatureWorkerSettings,
    redis: Redis,
    state: VehicleStateRepository,
    schedules: ScheduleRepository,
    deviations: CurrentDeviationRepository,
    predictor: PredictionPublisher,
) -> PredictionScheduler:
    return PredictionScheduler(
        redis=redis,
        state=state,
        deviations=deviations,
        schedules=schedules,
        predictor=predictor,
        point_ttl_s=settings.scheduler_point_ttl_s,
        rounding_s=settings.scheduler_rounding_s,
    )


# Запускает Feature Worker и освобождает ресурсы.
async def run_feature_worker() -> None:
    settings = FeatureWorkerSettings()
    redis = Redis.from_url(
        settings.redis_url,
        decode_responses=False,
    )
    consumer, scheduler = create_feature_worker(settings, redis)
    tasks = [
        asyncio.create_task(consumer.run()),
        asyncio.create_task(
            run_scheduler_loop(
                scheduler,
                settings.scheduler_period_s,
            )
        ),
    ]
    try:
        await redis.ping()
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        with suppress(Exception):
            await asyncio.gather(*tasks, return_exceptions=True)
        await redis.aclose()


# Настраивает журналирование и запускает Feature Worker.
def main() -> None:
    settings = FeatureWorkerSettings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_feature_worker())


if __name__ == "__main__":
    main()
