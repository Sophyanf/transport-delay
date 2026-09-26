from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class FeatureWorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    redis_url: str = "redis://redis:6379/0"

    telemetry_stream: str = "telemetry.v1"
    telemetry_dead_letter_stream: str = "telemetry.dead-letter.v1"
    prediction_stream: str = "predictions.v1"

    feature_worker_group: str = "feature-worker"
    feature_worker_consumer: str = "feature-worker-1"

    vehicle_state_prefix: str = "vehicle-state"
    vehicle_state_retention_s: int = Field(default=1_200, ge=900)
    current_deviation_prefix: str = "current-deviation"

    schedule_path: Path = Path("/workspace/data/runtime/schedule_plan.csv")
    ml_service_url: str = "http://ml-service:8001/api/v1"
    scheduler_period_s: float = Field(default=30.0, gt=0)
    scheduler_point_ttl_s: int = Field(default=1_800, gt=0)
    scheduler_rounding_s: int = Field(default=30, gt=0)

    stream_read_count: int = Field(default=200, gt=0)
    stream_block_ms: int = Field(default=5_000, gt=0)
    prediction_stream_maxlen: int = Field(default=100_000, gt=0)

    ml_request_timeout_s: float = Field(default=10.0, gt=0)
    log_level: str = "INFO"
