import logging

from redis.asyncio import Redis
from redis.exceptions import ResponseError
from transport_contracts import PredictionResultStreamEvent

from transport_backend.alerts import AlertService
from transport_backend.repositories import IncidentRepository
from transport_backend.websocket import WebSocketHub

LOGGER = logging.getLogger(__name__)


class PredictionConsumer:
    # Создаёт потребителя результатов прогнозирования.
    def __init__(
        self,
        redis: Redis,
        stream: str,
        group: str,
        consumer: str,
        repository: IncidentRepository,
        alerts: AlertService,
        websocket_hub: WebSocketHub,
        read_count: int,
        block_ms: int,
    ) -> None:
        self._redis = redis
        self._stream = stream
        self._group = group
        self._consumer = consumer
        self._repository = repository
        self._alerts = alerts
        self._websocket_hub = websocket_hub
        self._read_count = read_count
        self._block_ms = block_ms

    # Создаёт группу и непрерывно читает прогнозы.
    async def run(self) -> None:
        await self._run_ensure_group()
        while True:
            messages = await self._run_read()
            for message_id, fields in messages:
                await self._run_process(message_id, fields)

    # Создаёт consumer group при первом запуске.
    async def _run_ensure_group(self) -> None:
        try:
            await self._redis.xgroup_create(
                self._stream,
                self._group,
                id="0",
                mkstream=True,
            )
        except ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise

    # Читает очередную пачку прогнозов.
    async def _run_read(
        self,
    ) -> list[tuple[object, dict[object, object]]]:
        response = await self._redis.xreadgroup(
            self._group,
            self._consumer,
            {self._stream: ">"},
            count=self._read_count,
            block=self._block_ms,
        )
        if not response:
            return []
        return list(response[0][1])

    # Сохраняет один прогноз и уведомляет дашборд.
    async def _run_process(
        self,
        message_id: object,
        fields: dict[object, object],
    ) -> None:
        try:
            payload = self._run_payload(fields)
            event = PredictionResultStreamEvent.model_validate_json(payload)
            incident = self._alerts.create_incident(event.payload)
            saved = await self._repository.save(incident)
            await self._websocket_hub.broadcast(
                {
                    "type": "incident.updated",
                    "payload": saved,
                }
            )
            await self._run_acknowledge(message_id)
        except (TypeError, ValueError) as error:
            LOGGER.exception("Prediction message rejected: %s", error)
            await self._run_acknowledge(message_id)
        except Exception:
            LOGGER.exception("Prediction processing failed")

    # Подтверждает обработку сообщения.
    async def _run_acknowledge(self, message_id: object) -> None:
        await self._redis.xack(
            self._stream,
            self._group,
            message_id,
        )

    # Извлекает JSON payload сообщения.
    def _run_payload(
        self,
        fields: dict[object, object],
    ) -> str | bytes:
        payload = fields.get("payload", fields.get(b"payload"))
        if not isinstance(payload, (str, bytes)):
            raise ValueError("Prediction message has no payload")
        return payload
