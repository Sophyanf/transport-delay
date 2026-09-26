import logging

from redis.asyncio import Redis
from redis.exceptions import ResponseError
from transport_contracts import TelemetryStreamEvent

from transport_feature_worker.state import VehicleStateRepository

LOGGER = logging.getLogger(__name__)


class TelemetryConsumer:
    # Создаёт потребителя потока телеметрии.
    def __init__(
        self,
        redis: Redis,
        stream: str,
        group: str,
        consumer: str,
        state: VehicleStateRepository,
        read_count: int,
        block_ms: int,
    ) -> None:
        self._redis = redis
        self._stream = stream
        self._group = group
        self._consumer = consumer
        self._state = state
        self._read_count = read_count
        self._block_ms = block_ms

    # Создаёт группу и непрерывно читает телеметрию.
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

    # Читает очередную пачку телеметрии.
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

    # Валидирует, сохраняет и подтверждает сообщение.
    async def _run_process(
        self,
        message_id: object,
        fields: dict[object, object],
    ) -> None:
        try:
            payload = self._run_payload(fields)
            event = TelemetryStreamEvent.model_validate_json(payload)
            await self._state.append(event.payload)
            await self._redis.xack(
                self._stream,
                self._group,
                message_id,
            )
        except (TypeError, ValueError) as error:
            LOGGER.exception("Telemetry message rejected: %s", error)

    # Извлекает JSON payload сообщения Redis.
    def _run_payload(
        self,
        fields: dict[object, object],
    ) -> str | bytes:
        payload = fields.get("payload", fields.get(b"payload"))
        if not isinstance(payload, (str, bytes)):
            raise ValueError("Stream message has no payload")
        return payload
