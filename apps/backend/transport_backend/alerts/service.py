from datetime import UTC, datetime
from typing import Any

from transport_contracts import (
    IncidentStatus,
    PredictionResponse,
    RiskLevel,
)


class AlertService:
    # Преобразует прогноз модели в диспетчерский инцидент.
    def create_incident(
        self,
        prediction: PredictionResponse,
    ) -> dict[str, Any]:
        timestamp = datetime.now(UTC).isoformat()
        return {
            "incident_id": prediction.sample_id,
            "sample_id": prediction.sample_id,
            "tr_id": prediction.tr_id,
            "route": None,
            "vehicle_number": None,
            "prediction_time": prediction.prediction_time.isoformat(),
            "target_stop_id": prediction.target_stop_id,
            "target_time_begin": prediction.target_time_begin.isoformat(),
            "longitude": prediction.longitude,
            "latitude": prediction.latitude,
            "prediction_s": prediction.prediction_s,
            "predicted_delay_s": prediction.prediction_s,
            "predicted_delta_s": prediction.predicted_delta_s,
            "prob": prediction.confidence,
            "risk_level": prediction.risk_level.value,
            "confidence": prediction.confidence,
            "reason_code": prediction.reason_code,
            "reason_text": self._reason_text(prediction.reason_code),
            "recommendation": self._recommendation(prediction.reason_code),
            "segment_from": None,
            "segment_to": None,
            "status": self._status(prediction.risk_level).value,
            "acknowledged": False,
            "model_name": prediction.model_name,
            "model_version": prediction.model_version,
            "created_at": timestamp,
            "updated_at": timestamp,
        }

    # Возвращает текст причины инцидента.
    def _reason_text(self, code: str) -> str:
        reasons = {
            "STALE_TELEMETRY": "Телеметрия давно не обновлялась",
            "LONG_STOP": "Зафиксирован длительный простой",
            "INSUFFICIENT_SPEED": "Недостаточная скорость движения",
            "SPEED_DECREASING": "Скорость транспортного средства снижается",
            "DELAY_GROWTH": "Прогнозируется накопление задержки",
            "NORMAL_MOVEMENT": "Движение соответствует графику",
        }
        return reasons.get(code, "Причина требует проверки")

    # Возвращает рекомендацию диспетчеру.
    def _recommendation(self, code: str) -> str:
        recommendations = {
            "STALE_TELEMETRY": "Проверить связь с бортовым терминалом",
            "LONG_STOP": "Проверить причину простоя и состояние ТС",
            "INSUFFICIENT_SPEED": "Оценить дорожную обстановку",
            "SPEED_DECREASING": "Проверить возможный затор впереди",
            "DELAY_GROWTH": "Рассмотреть корректировку интервала",
            "NORMAL_MOVEMENT": "Дополнительные действия не требуются",
        }
        return recommendations.get(code, "Проверить ситуацию")

    # Определяет статус инцидента.
    def _status(self, risk: RiskLevel) -> IncidentStatus:
        if risk == RiskLevel.RED:
            return IncidentStatus.CRITICAL
        if risk == RiskLevel.YELLOW:
            return IncidentStatus.WARNING
        return IncidentStatus.NORMAL
