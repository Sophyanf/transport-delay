import json
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis
from transport_contracts import TelemetryEvent


class VehicleRepository:
    # Создаёт репозиторий последних состояний транспорта.
    def __init__(
        self,
        redis: Redis,
        state_prefix: str,
        fresh_s: int,
        stale_s: int,
    ) -> None:
        self._redis = redis
        self._state_prefix = state_prefix
        self._fresh_s = fresh_s
        self._stale_s = stale_s

    # Возвращает последнее состояние заданного ТС.
    async def get_latest(
        self,
        tr_id: str,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        values = await self._redis.zrevrange(
            self._state_key(tr_id),
            0,
            0,
        )
        if not values:
            return None
        event = self._parse_event(values[0])
        return self._event_to_position(event, now or datetime.now(UTC))

    # Возвращает последние позиции всех активных ТС.
    async def list_positions(self) -> list[dict[str, Any]]:
        now = datetime.now(UTC)
        identifiers = await self._active_vehicle_ids()
        positions: list[dict[str, Any]] = []
        for tr_id in identifiers:
            position = await self.get_latest(tr_id, now)
            if position is not None:
                positions.append(position)
        return positions

    # Дополняет инцидент данными последней телеметрии.
    async def enrich_incident(
        self,
        incident: dict[str, Any],
    ) -> dict[str, Any]:
        result = dict(incident)
        position = await self.get_latest(str(result["tr_id"]))
        defaults = self._empty_connection_fields()
        result.update(position or defaults)
        return result

    # Возвращает идентификаторы ТС из Redis.
    async def _active_vehicle_ids(self) -> list[str]:
        result: list[str] = []
        pattern = f"{self._state_prefix}:*"
        async for key in self._redis.scan_iter(match=pattern, count=500):
            text = self._text(key)
            result.append(text.removeprefix(f"{self._state_prefix}:"))
        return sorted(set(result))

    # Преобразует событие в позицию для API.
    def _event_to_position(
        self,
        event: TelemetryEvent,
        now: datetime,
    ) -> dict[str, Any]:
        seconds = max(0, int((now - event.event_time).total_seconds()))
        return {
            "tr_id": event.tr_id,
            "lat": event.latitude,
            "lon": event.longitude,
            "latitude": event.latitude,
            "longitude": event.longitude,
            "speed": event.speed_kmh,
            "heading": event.heading_deg,
            "last_seen_at": event.event_time.astimezone(UTC).strftime("%H:%M:%S"),
            "last_seen_iso": event.event_time.astimezone(UTC).isoformat(),
            "seconds_since_update": seconds,
            "connection_level": self._connection_level(seconds),
            "telemetry_stale": seconds > self._stale_s,
        }

    # Возвращает пустые поля при отсутствии телеметрии.
    def _empty_connection_fields(self) -> dict[str, Any]:
        return {
            "last_seen_at": None,
            "last_seen_iso": None,
            "seconds_since_update": None,
            "connection_level": "unknown",
            "telemetry_stale": True,
        }

    # Определяет цветовой уровень свежести телеметрии.
    def _connection_level(self, seconds: int) -> str:
        if seconds <= self._fresh_s:
            return "green"
        if seconds <= self._stale_s:
            return "yellow"
        return "red"

    # Восстанавливает TelemetryEvent из Redis Sorted Set.
    def _parse_event(self, value: object) -> TelemetryEvent:
        text = self._text(value)
        _, payload = text.split("|", maxsplit=1)
        return TelemetryEvent.model_validate(json.loads(payload))

    # Создаёт ключ состояния ТС.
    def _state_key(self, tr_id: str) -> str:
        return f"{self._state_prefix}:{tr_id}"

    # Преобразует Redis-значение в строку.
    def _text(self, value: object) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)
