from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class MlServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    active_model_config: Path = Path("/workspace/ml/configs/active_model.yaml")
    model_root: Path = Path("/workspace/ml/models")
    ml_service_host: str = "0.0.0.0"
    ml_service_port: int = 8001
    log_level: str = "INFO"
