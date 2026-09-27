import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from redis.asyncio import Redis


# Описывает запрос на What-if анализ.
class WhatIfRequest(BaseModel):
    route_id: int
    date: str
    extra_vehicles: int = 1
    scenario: str = "peak_hour"


# Приводит bytes из Redis к строке.
def _to_text(value) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else value


# Создаёт роутер What-if анализа.
def create_what_if_router(redis: Redis) -> APIRouter:
    router = APIRouter(prefix="/what-if", tags=["What-If Analysis"])

    # Считает влияние дополнительного ТС на задержки маршрута.
    @router.post("/analyze")
    async def analyze(request: WhatIfRequest) -> dict:
        try:
            events = await redis.xrevrange("predictions.v1", count=50)
        except Exception:
            raise HTTPException(status_code=503, detail="Не удалось подключиться к Redis")

        if not events:
            raise HTTPException(status_code=404, detail="Нет данных для анализа. Проверьте поток телеметрии.")

        predictions = []
        for _, fields in events:
            try:
                # Redis может отдавать ключи как bytes, проверяем оба варианта.
                raw = fields.get("payload") or fields.get(b"payload")
                if raw is None:
                    continue
                payload = json.loads(raw)
                data = payload.get("payload", {})
                tr_id = _to_text(data.get("tr_id", ""))
                if data.get("route_id") == request.route_id or str(request.route_id) in tr_id:
                    predictions.append(data)
            except (json.JSONDecodeError, KeyError, AttributeError):
                continue

        if not predictions:
            raise HTTPException(status_code=404, detail=f"Нет прогнозов для маршрута {request.route_id}")

        # Текущая средняя задержка по прогнозам маршрута.
        base_avg_delay = sum(float(p.get("predicted_delta_s", 0)) for p in predictions) / len(predictions)

        # Эвристика: каждый лишний автобус снижает задержку на 15%, максимум 40%.
        reduction_factor = min(0.4, request.extra_vehicles * 0.15)
        simulated_avg_delay = base_avg_delay * (1 - reduction_factor)

        # Разброс задержек снижается вместе с интервалом движения.
        base_std_dev = abs(base_avg_delay) * 0.2
        simulated_std_dev = base_std_dev * (1 - reduction_factor * 0.5)
        reduction = base_avg_delay - simulated_avg_delay

        return {
            "scenario": request.scenario,
            "route_id": request.route_id,
            "date": request.date,
            "extra_vehicles_added": request.extra_vehicles,
            "metrics": {
                "current_avg_delay_s": round(base_avg_delay, 2),
                "simulated_avg_delay_s": round(simulated_avg_delay, 2),
                "delay_reduction_s": round(reduction, 2),
                "current_std_dev_s": round(base_std_dev, 2),
                "simulated_std_dev_s": round(simulated_std_dev, 2),
                "confidence": 0.85,
            },
            "recommendation": (
                "Рекомендуется добавить ТС" if reduction > 30 else "Эффект незначителен"
            ),
            "raw_sample_size": len(predictions),
        }

    return router
