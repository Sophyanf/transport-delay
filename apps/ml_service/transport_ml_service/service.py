from collections.abc import Mapping

import numpy as np
import pandas as pd
from transport_contracts import (
    PredictionRequest,
    PredictionResponse,
    PredictionStatus,
    RiskLevel,
)
from transport_model_core import ModelManager


class PredictionService:
    # Создаёт сервис модельного инференса.
    def __init__(self, manager: ModelManager) -> None:
        self._manager = manager

    # Выполняет единичный прогноз.
    def predict(
        self,
        request: PredictionRequest,
    ) -> PredictionResponse:
        frame = self._predict_frame([request])
        prediction = float(self._manager.predict(frame)[0])
        return self._predict_response(request, prediction)

    # Выполняет пакетный прогноз.
    def predict_batch(
        self,
        requests: list[PredictionRequest],
    ) -> list[PredictionResponse]:
        if not requests:
            return []
        frame = self._predict_frame(requests)
        predictions = self._manager.predict(frame)
        return [
            self._predict_response(request, float(prediction))
            for request, prediction in zip(
                requests,
                predictions,
                strict=True,
            )
        ]

    # Преобразует запросы в таблицу признаков.
    def _predict_frame(
        self,
        requests: list[PredictionRequest],
    ) -> pd.DataFrame:
        return pd.DataFrame([self._predict_row(request) for request in requests])

    # Преобразует один запрос в строку признаков.
    def _predict_row(
        self,
        request: PredictionRequest,
    ) -> dict[str, object]:
        row = dict(request.features)
        row["sample_id"] = request.sample_id
        row["tr_id"] = request.tr_id
        row["target_stop_id"] = request.target_stop_id
        row["cur_dev_s"] = request.cur_dev_s
        return row

    # Формирует публичный результат прогноза.
    def _predict_response(
        self,
        request: PredictionRequest,
        prediction: float,
    ) -> PredictionResponse:
        model = self._manager.current_model()
        delta = prediction - request.cur_dev_s
        return PredictionResponse(
            sample_id=request.sample_id,
            tr_id=request.tr_id,
            prediction_time=request.prediction_time,
            target_stop_id=request.target_stop_id,
            target_time_begin=request.target_time_begin,
            longitude=self._predict_optional_number(request.features.get("last_lon")),
            latitude=self._predict_optional_number(request.features.get("last_lat")),
            prediction_s=prediction,
            predicted_delta_s=delta,
            forecast_horizon_s=request.horizon_s(),
            risk_level=self._predict_risk(prediction, delta),
            confidence=self._predict_confidence(request.features),
            reason_code=self._predict_reason(request.features, delta),
            model_name=model.name,
            model_version=model.version,
            status=PredictionStatus.OK,
        )

    # Определяет цветовой уровень риска.
    def _predict_risk(
        self,
        prediction_s: float,
        delta_s: float,
    ) -> RiskLevel:
        if prediction_s > 120:
            return RiskLevel.RED
        if prediction_s > 60 or delta_s > 30:
            return RiskLevel.YELLOW
        return RiskLevel.GREEN

    # Оценивает доверие к прогнозу.
    def _predict_confidence(
        self,
        features: Mapping[str, object],
    ) -> float:
        age = self._predict_number(features.get("telemetry_age_s"))
        count = self._predict_number(features.get("packet_count_5m"))
        if not np.isfinite(age):
            return 0.2
        age_score = max(0.0, 1.0 - age / 300.0)
        count_score = min(1.0, max(0.0, count) / 15.0)
        result = 0.25 + 0.5 * age_score + 0.25 * count_score
        return float(np.clip(result, 0.0, 1.0))

    # Определяет предполагаемую причину задержки.
    def _predict_reason(
        self,
        features: Mapping[str, object],
        delta_s: float,
    ) -> str:
        age = self._predict_number(features.get("telemetry_age_s"))
        ratio = self._predict_number(features.get("speed_to_required_ratio"))
        stopped = self._predict_number(features.get("stopped_ratio_5m"))
        trend = self._predict_number(features.get("speed_trend_5m"))
        if np.isfinite(age) and age > 120:
            return "STALE_TELEMETRY"
        if np.isfinite(stopped) and stopped > 0.6:
            return "LONG_STOP"
        if np.isfinite(ratio) and ratio < 0.7:
            return "INSUFFICIENT_SPEED"
        if np.isfinite(trend) and trend < -3.0:
            return "SPEED_DECREASING"
        return "DELAY_GROWTH" if delta_s > 20 else "NORMAL_MOVEMENT"

    # Безопасно преобразует значение в число.
    def _predict_number(self, value: object) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float("nan")

    # Возвращает конечное число или None.
    def _predict_optional_number(
        self,
        value: object,
    ) -> float | None:
        number = self._predict_number(value)
        return number if np.isfinite(number) else None
