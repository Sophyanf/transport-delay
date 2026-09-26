from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
from transport_contracts import PredictionRequest, RiskLevel
from transport_ml_service.service import PredictionService


class FakeModel:
    name = "fake-model"
    version = "1.0.0"
    feature_names = ("cur_dev_s",)


class FakeManager:
    # Возвращает фиксированный прогноз.
    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return np.full(len(features), 150.0)

    # Возвращает тестовую активную модель.
    def current_model(self) -> FakeModel:
        return FakeModel()


# Создаёт тестовый запрос на прогноз.
def create_service_request() -> PredictionRequest:
    current_time = datetime.now(UTC)
    return PredictionRequest(
        sample_id="sample-1",
        tr_id="vehicle-1",
        prediction_time=current_time,
        target_stop_id="stop-1",
        target_time_begin=current_time + timedelta(minutes=12),
        cur_dev_s=60.0,
        features={
            "cur_dev_s": 60.0,
            "last_lon": 37.6,
            "last_lat": 55.7,
            "telemetry_age_s": 5.0,
            "packet_count_5m": 20.0,
            "stopped_ratio_5m": 0.1,
            "speed_to_required_ratio": 0.5,
            "speed_trend_5m": -1.0,
        },
    )


# Проверяет формирование результата инференса.
def test_prediction_service_returns_response() -> None:
    service = PredictionService(FakeManager())  # type: ignore[arg-type]
    response = service.predict(create_service_request())
    assert response.prediction_s == 150.0
    assert response.predicted_delta_s == 90.0
    assert response.risk_level == RiskLevel.RED
    assert response.forecast_horizon_s == 720.0
