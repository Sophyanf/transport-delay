import json
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis


class IncidentRepository:
    def __init__(self, redis: Redis, key_prefix: str, retention_s: int, index_limit: int) -> None:
        self._redis = redis
        self._key_prefix = key_prefix
        self._retention_s = retention_s
        self._index_limit = index_limit
        self._index_key = f"{key_prefix}:index"

    async def save(self, incident: dict[str, Any]) -> dict[str, Any]:
        prepared = await self._save_prepare(incident)
        incident_id = str(prepared["incident_id"])
        timestamp = self._save_timestamp(prepared)
        async with self._redis.pipeline(transaction=True) as pipeline:
            pipeline.set(
                self._save_key(incident_id),
                json.dumps(prepared, ensure_ascii=False),
                ex=self._retention_s,
            )
            pipeline.zadd(self._index_key, {incident_id: timestamp})
            pipeline.zremrangebyrank(self._index_key, 0, -(self._index_limit + 1))
            await pipeline.execute()
        return prepared

    async def _save_prepare(self, incident: dict[str, Any]) -> dict[str, Any]:
        prepared = dict(incident)
        incident_id = str(prepared["incident_id"])
        previous = await self.get(incident_id)
        if previous is not None:
            prepared["acknowledged"] = previous.get("acknowledged", False)
            prepared["created_at"] = previous.get("created_at", prepared.get("created_at"))
        prepared["updated_at"] = datetime.now(UTC).isoformat()
        return prepared

    async def get(self, incident_id: str) -> dict[str, Any] | None:
        value = await self._redis.get(self._save_key(incident_id))
        if value is None:
            return None
        return json.loads(self._get_text(value))

    async def list_recent(
        self,
        limit: int = 200,
        risk_level: str | None = None,
    ) -> list[dict[str, Any]]:
        identifiers = await self._redis.zrevrange(self._index_key, 0, max(0, limit - 1))
        incidents = await self._list_recent_values(identifiers)
        if risk_level is None:
            return incidents
        return [incident for incident in incidents if incident.get("risk_level") == risk_level]

    async def _list_recent_values(self, identifiers: list[object]) -> list[dict[str, Any]]:
        if not identifiers:
            return []
        keys = [self._save_key(self._get_text(identifier)) for identifier in identifiers]
        values = await self._redis.mget(keys)
        return [json.loads(self._get_text(value)) for value in values if value is not None]

    async def acknowledge(self, incident_id: str) -> dict[str, Any] | None:
        incident = await self.get(incident_id)
        if incident is None:
            return None
        incident["acknowledged"] = True
        incident["acknowledged_at"] = datetime.now(UTC).isoformat()
        return await self.save(incident)

    async def close(self, incident_id: str) -> dict[str, Any] | None:
        incident = await self.get(incident_id)
        if incident is None:
            return None
        incident["status"] = "closed"
        incident["closed_at"] = datetime.now(UTC).isoformat()
        return await self.save(incident)

    async def statistics(self) -> dict[str, float | int]:
        incidents = await self.list_recent(self._index_limit)
        predictions = [float(item.get("prediction_s", 0.0)) for item in incidents]
        return {
            "total": len(incidents),
            "red": self._statistics_risk(incidents, "red"),
            "yellow": self._statistics_risk(incidents, "yellow"),
            "green": self._statistics_risk(incidents, "green"),
            "average_delay_s": self._statistics_average(predictions),
        }

    def _statistics_risk(self, incidents: list[dict[str, Any]], risk_level: str) -> int:
        return sum(item.get("risk_level") == risk_level for item in incidents)

    @staticmethod
    def _statistics_average(values: list[float]) -> float:
        if not values:
            return 0.0
        return float(sum(values) / len(values))

    def _save_key(self, incident_id: str) -> str:
        return f"{self._key_prefix}:{incident_id}"

    def _save_timestamp(self, incident: dict[str, Any]) -> float:
        updated_at = str(incident["updated_at"])
        return datetime.fromisoformat(updated_at).timestamp()

    @staticmethod
    def _get_text(value: object) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)
