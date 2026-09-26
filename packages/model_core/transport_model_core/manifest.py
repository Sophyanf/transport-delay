from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=64)
    entrypoint: str = Field(pattern=r"^[A-Za-z0-9_./-]+\.py::[A-Za-z_][A-Za-z0-9_]*$")
    target_type: Literal["direct", "residual", "ensemble"]
    feature_set: str = Field(min_length=1)
    artifact: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Проверяет безопасность относительного пути артефакта.
    @model_validator(mode="after")
    def validate_artifact_path(self) -> "ModelManifest":
        artifact_path = Path(self.artifact)
        if artifact_path.is_absolute():
            raise ValueError("artifact must be a relative path")
        if ".." in artifact_path.parts:
            raise ValueError("artifact must remain inside plugin directory")
        return self


class ActiveModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plugin: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    version: str = Field(min_length=1, max_length=64)


# Загружает и проверяет манифест модели.
def load_model_manifest(path: Path) -> ModelManifest:
    payload = load_model_manifest_yaml(path)
    return ModelManifest.model_validate(payload)


# Загружает конфигурацию активной модели.
def load_active_model_config(path: Path) -> ActiveModelConfig:
    payload = load_model_manifest_yaml(path)
    return ActiveModelConfig.model_validate(payload)


# Читает YAML-файл в словарь.
def load_model_manifest_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as stream:
        payload = yaml.safe_load(stream)
    if not isinstance(payload, dict):
        raise ValueError(f"YAML root must be an object: {path}")
    return payload
