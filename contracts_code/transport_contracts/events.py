from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from transport_contracts.prediction import (
    PredictionRequest,
    PredictionResponse,
)
from transport_contracts.telemetry import TelemetryEvent


class TelemetryStreamEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    event_type: Literal["telemetry.received"] = "telemetry.received"
    produced_at: datetime
    payload: TelemetryEvent


class PredictionRequestStreamEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    event_type: Literal["prediction.requested"] = "prediction.requested"
    produced_at: datetime
    payload: PredictionRequest


class PredictionResultStreamEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    event_type: Literal["prediction.completed"] = "prediction.completed"
    produced_at: datetime
    payload: PredictionResponse


class DeadLetterEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    event_type: Literal["message.rejected"] = "message.rejected"
    produced_at: datetime
    source_stream: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    original_payload: str
