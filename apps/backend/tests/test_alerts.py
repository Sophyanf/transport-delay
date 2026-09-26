from datetime import UTC, datetime, timedelta

from transport_backend.alerts import AlertService
from transport_contracts import (
    PredictionResponse,
    PredictionStatus,
    RiskLevel,
)


# Создаёт тестовый результат прогнозирования.
def create_alert_prediction(
    risk_level: RiskLevel,
    reason_code: str,
) -> PredictionResponse:
    current_time = datetime.now(UTC)
    return PredictionResponse(
        sample_id="sample-1",
        tr_id="vehicle-1",
        prediction_time=current_time,
        target_stop_id="stop-1",
        target_time_begin=current_time + timedelta(minutes=12),
        longitude=37.6,
        latitude=55.7,
        prediction_s=150.0,
        predicted_delta_s=60.0,
        forecast_horizon_s=720.0,
        risk_level=risk_level,
        confidence=0.9,
        reason_code=reason_code,
        model_name="test-model",
        model_version="1.0.0",
        status=PredictionStatus.OK,
    )


# Проверяет создание критического инцидента.
def test_alert_service_creates_critical_incident() -> None:
    prediction = create_alert_prediction(
        RiskLevel.RED,
        "INSUFFICIENT_SPEED",
    )
    incident = AlertService().create_incident(prediction)
    assert incident["status"] == "critical"
    assert incident["risk_level"] == "red"
    assert incident["tr_id"] == "vehicle-1"
    assert "дорожную обстановку" in incident["recommendation"]


# Проверяет создание предупреждения среднего риска.
def test_alert_service_creates_warning_incident() -> None:
    prediction = create_alert_prediction(
        RiskLevel.YELLOW,
        "SPEED_DECREASING",
    )
    incident = AlertService().create_incident(prediction)
    assert incident["status"] == "warning"
    assert incident["reason_code"] == "SPEED_DECREASING"


# Проверяет нормальное состояние низкого риска.
def test_alert_service_creates_normal_incident() -> None:
    prediction = create_alert_prediction(
        RiskLevel.GREEN,
        "NORMAL_MOVEMENT",
    )
    incident = AlertService().create_incident(prediction)
    assert incident["status"] == "normal"
