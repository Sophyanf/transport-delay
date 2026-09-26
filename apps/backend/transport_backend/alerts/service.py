from datetime import UTC, datetime
from typing import Any

from transport_contracts import (
    IncidentStatus,
    PredictionResponse,
    RiskLevel,
)


class AlertService:
    def create_incident(self, prediction: PredictionResponse) -> dict[str, Any]:
        return {
            "incident_id": prediction.sample_id,
            "sample_id": prediction.sample_id,
            "tr_id": prediction.tr_id,
            "prediction_time": prediction.prediction_time.isoformat(),
            "target_stop_id": prediction.target_stop_id,
            "target_time_begin": prediction.target_time_begin.isoformat(),
            "longitude": prediction.longitude,
            "latitude": prediction.latitude,
            "prediction_s": prediction.prediction_s,
            "predicted_delta_s": prediction.predicted_delta_s,
            "forecast_horizon_s": prediction.forecast_horizon_s,
            "risk_level": prediction.risk_level.value,
            "confidence": prediction.confidence,
            "reason_code": prediction.reason_code,
            "reason_text": self._create_incident_reason(prediction),
            "recommendation": self._create_incident_recommendation(prediction),
            "status": self._create_incident_status(prediction).value,
            "model_name": prediction.model_name,
            "model_version": prediction.model_version,
            "acknowledged": False,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }

    def _create_incident_reason(self, prediction: PredictionResponse) -> str:
        reasons = {
            "STALE_TELEMETRY": "Телеметрия давно не обновлялась",
            "LONG_STOP": "Зафиксирована длительная остановка",
            "INSUFFICIENT_SPEED": "Скорость недостаточна для прибытия по плану",
            "SPEED_DECREASING": "Скорость транспортного средства снижается",
            "DELAY_GROWTH": "Прогнозируется накопление задержки",
            "NORMAL_MOVEMENT": "Движение соответствует обычному режиму",
        }
        return reasons.get(prediction.reason_code, "Причина требует проверки диспетчером")

    def _create_incident_recommendation(self, prediction: PredictionResponse) -> str:
        recommendations = {
            "STALE_TELEMETRY": "Проверить связь с бортовым терминалом",
            "LONG_STOP": "Проверить причину остановки и состояние ТС",
            "INSUFFICIENT_SPEED": "Оценить дорожную обстановку на участке",
            "SPEED_DECREASING": "Проверить возможный затор впереди",
            "DELAY_GROWTH": "Рассмотреть корректировку интервала движения",
            "NORMAL_MOVEMENT": "Дополнительные действия не требуются",
        }
        default_recommendation = "Проверить ситуацию и выбрать корректирующее действие"
        return recommendations.get(prediction.reason_code, default_recommendation)

    def _create_incident_status(self, prediction: PredictionResponse) -> IncidentStatus:
        if prediction.risk_level == RiskLevel.RED:
            return IncidentStatus.CRITICAL
        if prediction.risk_level == RiskLevel.YELLOW:
            return IncidentStatus.WARNING
        return IncidentStatus.NORMAL
