import json
import logging
import math
from datetime import UTC, datetime

import httpx
from redis.asyncio import Redis
from transport_contracts import (
    PredictionRequest,
    PredictionResponse,
    PredictionResultStreamEvent,
)

logger = logging.getLogger(__name__)


class PredictionPublisher:
    # Создаёт клиент ML-service и издателя прогнозов.
    def __init__(
        self,
        redis: Redis,
        ml_service_url: str,
        prediction_stream: str,
        prediction_stream_maxlen: int,
        timeout_s: float,
    ) -> None:
        self._redis = redis
        self._ml_service_url = ml_service_url.rstrip("/")
        self._prediction_stream = prediction_stream
        self._prediction_stream_maxlen = prediction_stream_maxlen
        self._timeout_s = timeout_s

    # Выполняет прогноз и публикует результат.
    async def predict_and_publish(
        self,
        request: PredictionRequest,
    ) -> PredictionResponse:
        prediction = await self._predict_and_publish_request(request)
        await self._predict_and_publish_result(prediction)
        return prediction

    # Отправляет JSON-запрос в ML-service с заменой NaN на null.
    async def _predict_and_publish_request(
        self,
        request: PredictionRequest,
    ) -> PredictionResponse:
        payload = self._predict_and_publish_payload(request)

        async with httpx.AsyncClient(
            timeout=self._timeout_s,
        ) as client:
            response = await client.post(
                f"{self._ml_service_url}/predict",
                content=payload,
                headers={"Content-Type": "application/json"},
            )

        if response.status_code >= 400:
            logger.error(
                "ML-service ответил %s: %s",
                response.status_code,
                response.text[:2000],
            )
        response.raise_for_status()
        return PredictionResponse.model_validate(response.json())

    # Сериализует Pydantic-контракт в стандартный JSON без NaN.
    def _predict_and_publish_payload(
        self,
        request: PredictionRequest,
    ) -> str:
        data = request.model_dump(mode="json")
        return json.dumps(self._replace_non_finite(data))

    # Рекурсивно заменяет NaN и Infinity на None.
    @staticmethod
    def _replace_non_finite(value: object) -> object:
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, dict):
            return {
                key: PredictionPublisher._replace_non_finite(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                PredictionPublisher._replace_non_finite(item)
                for item in value
            ]
        return value

    # Публикует результат модели в Redis Streams.
    async def _predict_and_publish_result(
        self,
        prediction: PredictionResponse,
    ) -> None:
        event = PredictionResultStreamEvent(
            produced_at=datetime.now(UTC),
            payload=prediction,
        )
        await self._redis.xadd(
            self._prediction_stream,
            {"payload": event.model_dump_json()},
            maxlen=self._prediction_stream_maxlen,
            approximate=True,
        )
