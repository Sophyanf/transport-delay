from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from transport_contracts import (
    PredictionRequest,
    ReloadRequest,
    TelemetryEvent,
)


# Создаёт валидное тестовое событие телеметрии.
def create_test_telemetry() -> TelemetryEvent:
    current_time = datetime.now(UTC)
    return TelemetryEvent(
        event_id="unit-42:packet-10",
        tr_id="vehicle-42",
        unit_id="42",
        event_time=current_time,
        received_at=current_time + timedelta(seconds=1),
        longitude=37.6173,
        latitude=55.7558,
        speed_kmh=22.5,
        heading_deg=180.0,
        location_valid=True,
    )


# Создаёт валидный тестовый запрос на прогноз.
def create_test_prediction_request() -> PredictionRequest:
    current_time = datetime.now(UTC)
    return PredictionRequest(
        sample_id="vehicle-42:stop-10:1000",
        tr_id="vehicle-42",
        prediction_time=current_time,
        target_stop_id="stop-10",
        target_time_begin=current_time + timedelta(minutes=12),
        cur_dev_s=30.0,
        features={
            "cur_dev_s": 30.0,
            "last_speed": 22.5,
        },
    )


# Проверяет распознавание валидной геопозиции.
def test_telemetry_has_valid_location() -> None:
    telemetry = create_test_telemetry()
    assert telemetry.has_valid_location()


# Проверяет запрет неполной пары координат.
def test_telemetry_rejects_partial_coordinates() -> None:
    payload = create_test_telemetry().model_dump()
    payload["latitude"] = None
    with pytest.raises(ValidationError):
        TelemetryEvent.model_validate(payload)


# Проверяет расчёт конкурсного горизонта.
def test_prediction_request_has_competition_horizon() -> None:
    request = create_test_prediction_request()
    assert request.horizon_s() == 720.0
    assert request.has_competition_horizon()


# Проверяет запрет целевого времени в прошлом.
def test_prediction_request_rejects_past_target() -> None:
    request = create_test_prediction_request()
    payload = request.model_dump()
    payload["target_time_begin"] = request.prediction_time - timedelta(seconds=1)
    with pytest.raises(ValidationError):
        PredictionRequest.model_validate(payload)


# Проверяет одновременную передачу имени и версии модели.
def test_reload_request_rejects_incomplete_pair() -> None:
    with pytest.raises(ValidationError):
        ReloadRequest(plugin="catboost_residual_v1")


# Проверяет JSON-сериализацию события телеметрии.
def test_telemetry_json_round_trip() -> None:
    telemetry = create_test_telemetry()
    restored = TelemetryEvent.model_validate_json(telemetry.model_dump_json())
    assert restored == telemetry
