from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    feature_set: str = Field(min_length=1)
    target_type: str = Field(min_length=1)
    loaded: bool
    artifact_path: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReloadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plugin: str | None = Field(default=None, min_length=1)
    version: str | None = Field(default=None, min_length=1)

    # Требует одновременно передавать имя и версию модели.
    @model_validator(mode="after")
    def validate_reload_pair(self) -> "ReloadRequest":
        plugin_missing = self.plugin is None
        version_missing = self.version is None
        if plugin_missing != version_missing:
            raise ValueError("plugin and version must be provided together")
        return self


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "degraded", "not_ready"]
    service: str = Field(min_length=1)
    active_model: str | None = None
    active_version: str | None = None
    details: dict[str, str] = Field(default_factory=dict)
