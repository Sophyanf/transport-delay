from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
from transport_contracts import PredictionRequest
from transport_ml_service.service import PredictionService
from transport_model_core import ModelLoader, ModelManager

MODEL_REPLACEMENT_SOURCE = """
import numpy as np

class ReplaceableDelayModel:
    def __init__(self, manifest, plugin_directory):
        self.name = manifest.name
        self.version = manifest.version
        self.feature_names = ("cur_dev_s",)
        self._artifact = plugin_directory / manifest.artifact
        self._offset = 0.0

    def fit(self, features, target):
        residual = target - features["cur_dev_s"]
        self._offset = float(residual.median())

    def predict(self, features):
        baseline = features["cur_dev_s"].to_numpy(dtype=float)
        return baseline + self._offset

    def load(self):
        self._offset = float(
            self._artifact.read_text(encoding="utf-8")
        )

    def save(self):
        self._artifact.parent.mkdir(parents=True, exist_ok=True)
        self._artifact.write_text(
            str(self._offset),
            encoding="utf-8",
        )
"""


# Создаёт тестовый модельный плагин с заданной поправкой.
def create_model_replacement_plugin(
    root: Path,
    plugin: str,
    model_name: str,
    offset: float,
) -> None:
    plugin_directory = root / plugin
    artifact_directory = plugin_directory / "artifacts"
    artifact_directory.mkdir(parents=True)
    create_model_replacement_manifest(
        plugin_directory,
        model_name,
    )
    (plugin_directory / "model.py").write_text(
        MODEL_REPLACEMENT_SOURCE,
        encoding="utf-8",
    )
    (artifact_directory / "offset.txt").write_text(
        str(offset),
        encoding="utf-8",
    )


# Создаёт манифест тестового плагина.
def create_model_replacement_manifest(
    plugin_directory: Path,
    model_name: str,
) -> None:
    content = "\n".join(
        [
            f"name: {model_name}",
            "version: 1.0.0",
            "entrypoint: model.py::ReplaceableDelayModel",
            "target_type: residual",
            "feature_set: feature_set_v1",
            "artifact: artifacts/offset.txt",
        ]
    )
    (plugin_directory / "model.yaml").write_text(
        content,
        encoding="utf-8",
    )


# Создаёт конфигурацию исходной активной модели.
def create_model_replacement_config(
    path: Path,
    plugin: str,
) -> None:
    path.write_text(
        f"plugin: {plugin}\nversion: 1.0.0\n",
        encoding="utf-8",
    )


# Создаёт запрос для проверки ML-service.
def create_model_replacement_request() -> PredictionRequest:
    current_time = datetime.now(UTC)
    return PredictionRequest(
        sample_id="replacement-test",
        tr_id="vehicle-1",
        prediction_time=current_time,
        target_stop_id="stop-1",
        target_time_begin=current_time + timedelta(minutes=12),
        cur_dev_s=30.0,
        features={
            "cur_dev_s": 30.0,
            "telemetry_age_s": 5.0,
            "packet_count_5m": 10.0,
        },
    )


# Проверяет замену модели без изменения ML-service.
def test_model_replacement_changes_service_prediction(
    tmp_path: Path,
) -> None:
    model_root = tmp_path / "models"
    model_root.mkdir()
    create_model_replacement_plugin(
        model_root,
        "model_a",
        "model-a",
        10.0,
    )
    create_model_replacement_plugin(
        model_root,
        "model_b",
        "model-b",
        70.0,
    )
    config_path = tmp_path / "active_model.yaml"
    create_model_replacement_config(config_path, "model_a")
    manager = ModelManager(
        ModelLoader(model_root),
        config_path,
    )
    service = PredictionService(manager)

    manager.load_active()
    first = service.predict(create_model_replacement_request())

    manager.reload("model_b", "1.0.0")
    second = service.predict(create_model_replacement_request())

    assert first.prediction_s == 40.0
    assert first.model_name == "model-a"
    assert second.prediction_s == 100.0
    assert second.model_name == "model-b"


# Проверяет сохранение старой модели при ошибке reload.
def test_model_replacement_keeps_previous_on_failure(
    tmp_path: Path,
) -> None:
    model_root = tmp_path / "models"
    model_root.mkdir()
    create_model_replacement_plugin(
        model_root,
        "stable_model",
        "stable-model",
        15.0,
    )
    config_path = tmp_path / "active_model.yaml"
    create_model_replacement_config(
        config_path,
        "stable_model",
    )
    manager = ModelManager(
        ModelLoader(model_root),
        config_path,
    )
    manager.load_active()

    with suppress(FileNotFoundError):
        manager.reload("missing_model", "1.0.0")

    frame = pd.DataFrame({"cur_dev_s": [20.0]})
    prediction = manager.predict(frame)

    assert prediction.tolist() == [35.0]
    assert manager.current_model().name == "stable-model"
