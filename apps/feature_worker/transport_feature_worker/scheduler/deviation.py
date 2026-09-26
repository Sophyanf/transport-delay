from dataclasses import dataclass
from datetime import UTC, datetime

from redis.asyncio import Redis


@dataclass(frozen=True)
class CurrentDeviation:
    deviation_s: float
    updated_at: datetime


class CurrentDeviationRepository:
    # Создаёт хранилище текущего отклонения от расписания.
    def __init__(
        self,
        redis: Redis,
        key_prefix: str,
    ) -> None:
        self._redis = redis
        self._key_prefix = key_prefix

    # Сохраняет последнее известное отклонение ТС.
    async def set(
        self,
        tr_id: str,
        deviation_s: float,
        updated_at: datetime | None = None,
    ) -> None:
        timestamp = updated_at or datetime.now(UTC)
        await self._redis.hset(
            self._set_key(tr_id),
            mapping={
                "deviation_s": str(float(deviation_s)),
                "updated_at": timestamp.isoformat(),
            },
        )
        await self._redis.expire(
            self._set_key(tr_id),
            86_400,
        )

    # Возвращает последнее известное отклонение ТС.
    async def get(
        self,
        tr_id: str,
    ) -> CurrentDeviation | None:
        values = await self._redis.hgetall(self._set_key(tr_id))
        if not values:
            return None
        normalized = self._get_normalize(values)
        return CurrentDeviation(
            deviation_s=float(normalized["deviation_s"]),
            updated_at=datetime.fromisoformat(normalized["updated_at"]),
        )

    # Возвращает значение отклонения с fallback.
    async def value(
        self,
        tr_id: str,
        fallback: float = 0.0,
    ) -> float:
        current = await self.get(tr_id)
        if current is None:
            return fallback
        return current.deviation_s

    # Создаёт Redis-ключ отклонения транспортного средства.
    def _set_key(self, tr_id: str) -> str:
        return f"{self._key_prefix}:{tr_id}"

    # Преобразует Redis hash к строковому словарю.
    def _get_normalize(
        self,
        values: dict[object, object],
    ) -> dict[str, str]:
        return {self._get_text(key): self._get_text(value) for key, value in values.items()}

    # Преобразует Redis-значение в строку.
    def _get_text(self, value: object) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)
