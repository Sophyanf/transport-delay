from datetime import UTC, datetime

import httpx
from redis.asyncio import Redis
from transport_contracts import (
    PredictionRequest,
    PredictionResponse,
    PredictionResultStreamEvent,
)


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

        response.raise_for_status()
        return PredictionResponse.model_validate(response.json())

    # Сериализует Pydantic-контракт в стандартный JSON.
    def _predict_and_publish_payload(
        self,
        request: PredictionRequest,
    ) -> str:
        return request.model_dump_json()

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
