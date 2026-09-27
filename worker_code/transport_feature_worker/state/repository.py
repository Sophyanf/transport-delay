from datetime import datetime

from redis.asyncio import Redis
from transport_contracts import TelemetryEvent


class VehicleStateRepository:
    # Создаёт хранилище краткосрочной истории телеметрии.
    def __init__(
        self,
        redis: Redis,
        key_prefix: str,
        retention_s: int,
    ) -> None:
        self._redis = redis
        self._key_prefix = key_prefix
        self._retention_s = retention_s

    # Добавляет событие в историю транспортного средства.
    async def append(self, event: TelemetryEvent) -> None:
        key = self._append_key(event.tr_id)
        score = event.event_time.timestamp()
        member = self._append_member(event)
        minimum_score = score - self._retention_s
        async with self._redis.pipeline(transaction=True) as pipeline:
            pipeline.zadd(key, {member: score})
            pipeline.zremrangebyscore(key, "-inf", minimum_score)
            pipeline.expire(key, self._retention_s * 2)
            await pipeline.execute()

    # Возвращает историю ТС до заданного момента включительно.
    async def history(
        self,
        tr_id: str,
        until: datetime,
    ) -> list[TelemetryEvent]:
        key = self._append_key(tr_id)
        minimum = until.timestamp() - self._retention_s
        maximum = until.timestamp()
        values = await self._redis.zrangebyscore(
            key,
            minimum,
            maximum,
        )
        return [self._history_parse_member(value) for value in values]

    # Возвращает идентификаторы активных транспортных средств.
    async def active_vehicle_ids(self) -> list[str]:
        pattern = f"{self._key_prefix}:*"
        identifiers: list[str] = []
        async for key in self._redis.scan_iter(
            match=pattern,
            count=500,
        ):
            identifiers.append(self._active_vehicle_id(key))
        return sorted(set(identifiers))

    # Возвращает последнее событие транспортного средства.
    async def latest(
        self,
        tr_id: str,
    ) -> TelemetryEvent | None:
        values = await self._redis.zrevrange(
            self._append_key(tr_id),
            0,
            0,
        )
        if not values:
            return None
        return self._history_parse_member(values[0])

    # Создаёт Redis-ключ истории транспортного средства.
    def _append_key(self, tr_id: str) -> str:
        return f"{self._key_prefix}:{tr_id}"

    # Сериализует событие в уникальный элемент sorted set.
    def _append_member(self, event: TelemetryEvent) -> str:
        return f"{event.event_id}|{event.model_dump_json()}"

    # Восстанавливает событие из элемента sorted set.
    def _history_parse_member(
        self,
        value: str | bytes,
    ) -> TelemetryEvent:
        text = value.decode("utf-8") if isinstance(value, bytes) else value
        _, payload = text.split("|", maxsplit=1)
        return TelemetryEvent.model_validate_json(payload)

    # Извлекает tr_id из Redis-ключа.
    def _active_vehicle_id(self, value: str | bytes) -> str:
        text = value.decode("utf-8") if isinstance(value, bytes) else value
        return text.removeprefix(f"{self._key_prefix}:")
