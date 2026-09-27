from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BackendSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    redis_url: str = "redis://redis:6379/0"
    prediction_stream: str = "predictions.v1"
    backend_prediction_group: str = "backend"
    backend_prediction_consumer: str = "backend-1"
    backend_stream_read_count: int = Field(default=200, gt=0)
    backend_stream_block_ms: int = Field(default=5_000, gt=0)

    incident_prefix: str = "incident"
    incident_retention_s: int = Field(default=604_800, gt=0)
    incident_index_limit: int = Field(default=10_000, gt=0)

    vehicle_state_prefix: str = "vehicle-state"
    telemetry_fresh_s: int = Field(default=15, gt=0)
    telemetry_stale_s: int = Field(default=60, gt=0)

    schedule_path: Path = Path("/workspace/data/runtime/schedule_plan.csv")
    score_points_path: Path = Path("/workspace/data/raw/labels/labels_test.csv")
    score_ground_truth_path: Path = Path("/workspace/data/raw/labels/labels_test.csv")
    score_history_key: str = "score-upload-history"
    score_history_limit: int = Field(default=100, gt=0)
    mae_target: float = 30.0

    validate_points_path: Path = Path("/workspace/data/raw/validate/points.csv")
    validate_predictions_path: Path = Path("/workspace/data/interim/validate_predictions.parquet")
    submission_path: Path = Path("/workspace/data/submissions/submission.csv")

    backend_host: str = "0.0.0.0"
    backend_port: int = Field(default=8_000, ge=1, le=65_535)
    log_level: str = "INFO"
