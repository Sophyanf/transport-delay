import logging
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from redis.asyncio import Redis
from transport_contracts import PredictionRequest, TelemetryEvent
from transport_features import FeatureBuilder

from transport_feature_worker.predictor import PredictionPublisher
from transport_feature_worker.scheduler.deviation import (
    CurrentDeviationRepository,
)
from transport_feature_worker.scheduler.schedule import (
    ScheduledStop,
    ScheduleRepository,
)
from transport_feature_worker.state import VehicleStateRepository

LOGGER = logging.getLogger(__name__)


class PredictionScheduler:
    # Создаёт планировщик online-прогнозов.
    def __init__(
        self,
        redis: Redis,
        state: VehicleStateRepository,
        deviations: CurrentDeviationRepository,
        schedules: ScheduleRepository,
        predictor: PredictionPublisher,
        point_ttl_s: int,
        rounding_s: int,
    ) -> None:
        self._redis = redis
        self._state = state
        self._deviations = deviations
        self._schedules = schedules
        self._predictor = predictor
        self._point_ttl_s = point_ttl_s
        self._rounding_s = rounding_s
        self._feature_builder = FeatureBuilder("feature_set_v1")

    # Создаёт прогнозы для всех активных ТС.
    async def run_once(
        self,
        current_time: datetime | None = None,
    ) -> int:
        prediction_time = current_time or datetime.now(UTC)
        vehicle_ids = await self._state.active_vehicle_ids()
        created = 0
        for tr_id in vehicle_ids:
            created += await self._run_once_vehicle(
                tr_id,
                prediction_time,
            )
        return created

    # Создаёт прогноз для одного транспортного средства.
    async def _run_once_vehicle(
        self,
        tr_id: str,
        prediction_time: datetime,
    ) -> int:
        target = self._schedules.target_stop(
            tr_id,
            prediction_time,
        )
        if target is None:
            return 0
        sample_id = self._run_once_sample_id(
            tr_id,
            target,
            prediction_time,
        )
        if not await self._run_once_claim(sample_id):
            return 0
        try:
            request = await self._run_once_request(
                sample_id,
                tr_id,
                target,
                prediction_time,
            )
            await self._predictor.predict_and_publish(request)
            return 1
        except Exception:
            await self._run_once_release(sample_id)
            LOGGER.exception("Prediction failed for %s", sample_id)
            return 0

    # Создаёт детерминированный sample_id online-прогноза.
    def _run_once_sample_id(
        self,
        tr_id: str,
        target: ScheduledStop,
        prediction_time: datetime,
    ) -> str:
        timestamp = int(prediction_time.timestamp())
        rounded = timestamp // self._rounding_s * self._rounding_s
        return f"{tr_id}_{target.stop_id}_{rounded}"

    # Захватывает прогнозную точку для защиты от дублей.
    async def _run_once_claim(self, sample_id: str) -> bool:
        result = await self._redis.set(
            f"prediction-point:{sample_id}",
            "1",
            ex=self._point_ttl_s,
            nx=True,
        )
        return bool(result)

    # Освобождает точку после неуспешного прогноза.
    async def _run_once_release(self, sample_id: str) -> None:
        await self._redis.delete(f"prediction-point:{sample_id}")

    # Формирует запрос к ML-service.
    async def _run_once_request(
        self,
        sample_id: str,
        tr_id: str,
        target: ScheduledStop,
        prediction_time: datetime,
    ) -> PredictionRequest:
        history = await self._state.history(tr_id, prediction_time)
        deviation = await self._deviations.value(tr_id)
        features = self._run_once_features(
            sample_id,
            tr_id,
            target,
            prediction_time,
            deviation,
            history,
        )
        return PredictionRequest(
            sample_id=sample_id,
            tr_id=tr_id,
            prediction_time=prediction_time,
            target_stop_id=target.stop_id,
            target_time_begin=target.planned_time,
            cur_dev_s=deviation,
            features=features,
        )

    # Строит признаки общей offline/online реализацией.
    def _run_once_features(
        self,
        sample_id: str,
        tr_id: str,
        target: ScheduledStop,
        prediction_time: datetime,
        deviation: float,
        history: list[TelemetryEvent],
    ) -> dict[str, Any]:
        points = self._run_once_points_frame(
            sample_id,
            tr_id,
            target,
            prediction_time,
            deviation,
        )
        traffic = self._run_once_traffic_frame(history)
        schedule = self._schedules.frame()
        frame = self._feature_builder.build(
            points,
            traffic,
            schedule,
        )
        return frame.iloc[0].to_dict()

    # Создаёт таблицу одной прогнозной точки.
    def _run_once_points_frame(
        self,
        sample_id: str,
        tr_id: str,
        target: ScheduledStop,
        prediction_time: datetime,
        deviation: float,
    ) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "sample_id": sample_id,
                    "tr_id": tr_id,
                    "T": prediction_time,
                    "target_stop_id": target.stop_id,
                    "target_time_begin": target.planned_time,
                    "cur_dev_s": deviation,
                }
            ]
        )

    # Преобразует историю контрактов в traffic DataFrame.
    def _run_once_traffic_frame(
        self,
        history: list[TelemetryEvent],
    ) -> pd.DataFrame:
        rows = [self._run_once_traffic_row(event) for event in history]
        if rows:
            return pd.DataFrame(rows)
        return self._run_once_empty_traffic()

    # Преобразует событие в строку телеметрии.
    def _run_once_traffic_row(
        self,
        event: TelemetryEvent,
    ) -> dict[str, object]:
        return {
            "tr_id": event.tr_id,
            "event_time": event.event_time,
            "receive_time": event.received_at,
            "speed": event.speed_kmh,
            "heading": event.heading_deg,
            "alt": event.altitude_m,
            "lon": event.longitude,
            "lat": event.latitude,
            "location_valid": event.location_valid,
            "is_hist_data": event.is_historical,
        }

    # Создаёт пустую таблицу обязательной traffic-схемы.
    def _run_once_empty_traffic(self) -> pd.DataFrame:
        return pd.DataFrame(
            columns=[
                "tr_id",
                "event_time",
                "receive_time",
                "speed",
                "heading",
                "alt",
                "lon",
                "lat",
                "location_valid",
                "is_hist_data",
            ]
        )
