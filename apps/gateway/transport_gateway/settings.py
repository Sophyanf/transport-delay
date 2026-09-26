from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    redis_url: str = "redis://redis:6379/0"
    telemetry_stream: str = "telemetry.v1"
    telemetry_dead_letter_stream: str = "telemetry.dead-letter.v1"
    telemetry_stream_maxlen: int = Field(default=200_000, gt=0)

    gateway_host: str = "0.0.0.0"
    gateway_port: int = Field(default=19_000, ge=1, le=65_535)
    gateway_decoder: Literal["json_lines", "ndtp"] = "json_lines"
    gateway_read_size: int = Field(default=65_536, ge=1)
    gateway_max_buffer_bytes: int = Field(
        default=1_048_576,
        ge=1_024,
    )
    gateway_client_timeout_s: float = Field(default=120.0, gt=0)
    log_level: str = "INFO"
