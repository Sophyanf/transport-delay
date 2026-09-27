from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from transport_contracts.common import PredictionStatus, RiskLevel

FeatureValue = float | int | str | bool | None


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    sample_id: str = Field(min_length=1, max_length=256)
    tr_id: str = Field(min_length=1, max_length=128)
    prediction_time: datetime
    target_stop_id: str = Field(min_length=1, max_length=256)
    target_time_begin: datetime
    cur_dev_s: float
    features: dict[str, FeatureValue]

    # Проверяет положительный горизонт прогнозирования.
    @model_validator(mode="after")
    def validate_prediction_horizon(self) -> "PredictionRequest":
        if self.horizon_s() <= 0:
            raise ValueError("target_time_begin must be later than prediction_time")
        return self

    # Возвращает горизонт прогнозирования в секундах.
    def horizon_s(self) -> float:
        difference = self.target_time_begin - self.prediction_time
        return float(difference.total_seconds())

    # Проверяет попадание горизонта в конкурсное окно.
    def has_competition_horizon(self) -> bool:
        return 600 < self.horizon_s() <= 900


class PredictionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    sample_id: str = Field(min_length=1, max_length=256)
    tr_id: str = Field(min_length=1, max_length=128)
    prediction_time: datetime
    target_stop_id: str = Field(min_length=1, max_length=256)
    target_time_begin: datetime
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    prediction_s: float
    predicted_delta_s: float
    forecast_horizon_s: float = Field(gt=0)
    risk_level: RiskLevel
    confidence: float = Field(ge=0, le=1)
    reason_code: str = Field(min_length=1, max_length=128)
    model_name: str = Field(min_length=1, max_length=128)
    model_version: str = Field(min_length=1, max_length=64)
    status: PredictionStatus = PredictionStatus.OK
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Проверяет совместное наличие координат результата.
    @model_validator(mode="after")
    def validate_response_coordinates(self) -> "PredictionResponse":
        longitude_missing = self.longitude is None
        latitude_missing = self.latitude is None
        if longitude_missing != latitude_missing:
            raise ValueError("longitude and latitude must be provided together")
        return self
