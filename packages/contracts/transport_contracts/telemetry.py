from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    event_id: str = Field(min_length=1, max_length=256)
    tr_id: str = Field(min_length=1, max_length=128)
    unit_id: str | None = Field(default=None, max_length=128)
    event_time: datetime
    received_at: datetime
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    altitude_m: float | None = None
    speed_kmh: float | None = Field(default=None, ge=0, le=300)
    heading_deg: float | None = Field(default=None, ge=0, lt=360)
    location_valid: bool = False
    packet_id: str | None = Field(default=None, max_length=128)
    device_event_id: str | None = Field(default=None, max_length=128)
    is_historical: bool = False
    source: str = Field(default="ndtp", min_length=1, max_length=64)

    # Проверяет совместное наличие широты и долготы.
    @model_validator(mode="after")
    def validate_coordinate_pair(self) -> "TelemetryEvent":
        longitude_missing = self.longitude is None
        latitude_missing = self.latitude is None
        if longitude_missing != latitude_missing:
            raise ValueError("longitude and latitude must be provided together")
        return self

    # Возвращает признак наличия достоверной геопозиции.
    def has_valid_location(self) -> bool:
        return self.location_valid and self.longitude is not None and self.latitude is not None
