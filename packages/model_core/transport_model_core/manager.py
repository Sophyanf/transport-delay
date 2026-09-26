from pathlib import Path
from threading import RLock

import numpy as np
import pandas as pd

from transport_model_core.loader import ModelLoader
from transport_model_core.manifest import (
    ActiveModelConfig,
    ModelManifest,
    load_active_model_config,
)
from transport_model_core.protocol import DelayModel


class ModelManager:
    # Создаёт менеджер активной модели.
    def __init__(
        self,
        loader: ModelLoader,
        active_config_path: Path,
    ) -> None:
        self._loader = loader
        self._active_config_path = active_config_path
        self._model: DelayModel | None = None
        self._config: ActiveModelConfig | None = None
        self._lock = RLock()

    # Загружает модель из active_model.yaml.
    def load_active(self) -> DelayModel:
        config = load_active_model_config(self._active_config_path)
        return self.reload(config.plugin, config.version)

    # Атомарно заменяет активную модель.
    def reload(
        self,
        plugin: str,
        version: str,
    ) -> DelayModel:
        candidate = self._loader.load(plugin, version)
        with self._lock:
            self._model = candidate
            self._config = ActiveModelConfig(
                plugin=plugin,
                version=version,
            )
        return candidate

    # Выполняет прогноз активной моделью.
    def predict(self, features: pd.DataFrame) -> np.ndarray:
        with self._lock:
            model = self._require_model()
            return model.predict(features)

    # Возвращает активную модель.
    def current_model(self) -> DelayModel:
        with self._lock:
            return self._require_model()

    # Возвращает копию активной конфигурации.
    def current_config(self) -> ActiveModelConfig:
        with self._lock:
            if self._config is None:
                raise RuntimeError("Active model is not configured")
            return self._config.model_copy()

    # Возвращает манифест активной модели.
    def current_manifest(self) -> ModelManifest:
        config = self.current_config()
        return self._loader.manifest(config.plugin)

    # Проверяет наличие загруженной модели.
    def is_ready(self) -> bool:
        with self._lock:
            return self._model is not None

    # Возвращает модель или сообщает об ошибке готовности.
    def _require_model(self) -> DelayModel:
        if self._model is None:
            raise RuntimeError("Model is not loaded")
        return self._model
