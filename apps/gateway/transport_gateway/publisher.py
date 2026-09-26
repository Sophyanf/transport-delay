from datetime import UTC, datetime

from redis.asyncio import Redis
from transport_contracts import (
    DeadLetterEvent,
    TelemetryEvent,
    TelemetryStreamEvent,
)


class TelemetryPublisher:
    # Создаёт издателя телеметрии и ошибочных сообщений.
    def __init__(
        self,
        redis: Redis,
        stream: str,
        dead_letter_stream: str,
        max_length: int,
    ) -> None:
        self._redis = redis
        self._stream = stream
        self._dead_letter_stream = dead_letter_stream
        self._max_length = max_length

    # Публикует валидное событие телеметрии.
    async def publish(self, telemetry: TelemetryEvent) -> str:
        event = TelemetryStreamEvent(
            produced_at=datetime.now(UTC),
            payload=telemetry,
        )
        message_id = await self._redis.xadd(
            self._stream,
            {"payload": event.model_dump_json()},
            maxlen=self._max_length,
            approximate=True,
        )
        return self._publish_message_id(message_id)

    # Публикует отклонённый пакет в dead-letter поток.
    async def publish_rejected(
        self,
        packet: bytes,
        reason: str,
    ) -> str:
        event = DeadLetterEvent(
            produced_at=datetime.now(UTC),
            source_stream=self._stream,
            reason=reason,
            original_payload=self._publish_packet_text(packet),
        )
        message_id = await self._redis.xadd(
            self._dead_letter_stream,
            {"payload": event.model_dump_json()},
            maxlen=self._max_length,
            approximate=True,
        )
        return self._publish_message_id(message_id)

    # Преобразует Redis message ID в строку.
    def _publish_message_id(self, value: object) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    # Представляет бинарный пакет безопасной строкой.
    def _publish_packet_text(self, packet: bytes) -> str:
        try:
            return packet.decode("utf-8")
        except UnicodeDecodeError:
            return packet.hex()
