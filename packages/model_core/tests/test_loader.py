from pathlib import Path

import numpy as np
import pandas as pd
from transport_model_core import ModelLoader

MODEL_SOURCE = """
import numpy as np

class ConstantDelayModel:
    name = "constant_delay"
    version = "1.0.0"
    feature_names = ("cur_dev_s",)

    def __init__(self, manifest, plugin_directory):
        self._value = 15.0

    def fit(self, features, target):
        self._value = float(target.median())

    def predict(self, features):
        return np.full(len(features), self._value, dtype=float)

    def load(self):
        return None

    def save(self):
        return None
"""


# Создаёт временный модельный плагин.
def create_loader_plugin(root: Path) -> None:
    plugin = root / "constant_v1"
    plugin.mkdir()
    (plugin / "model.yaml").write_text(
        "\n".join(
            [
                "name: constant_delay",
                "version: 1.0.0",
                "entrypoint: model.py::ConstantDelayModel",
                "target_type: direct",
                "feature_set: feature_set_v1",
                "artifact: artifacts/model.bin",
            ]
        ),
        encoding="utf-8",
    )
    (plugin / "model.py").write_text(
        MODEL_SOURCE,
        encoding="utf-8",
    )


# Проверяет динамическую загрузку модельного плагина.
def test_loader_loads_replaceable_plugin(tmp_path: Path) -> None:
    create_loader_plugin(tmp_path)
    loader = ModelLoader(tmp_path)
    model = loader.load("constant_v1", "1.0.0")
    features = pd.DataFrame({"cur_dev_s": [1.0, 2.0]})
    prediction = model.predict(features)
    np.testing.assert_array_equal(
        prediction,
        np.array([15.0, 15.0]),
    )


# Проверяет создание необученной модели.
def test_loader_creates_untrained_plugin(tmp_path: Path) -> None:
    create_loader_plugin(tmp_path)
    loader = ModelLoader(tmp_path)
    model = loader.create("constant_v1", "1.0.0")
    target = pd.Series([10.0, 20.0, 30.0])
    features = pd.DataFrame({"cur_dev_s": [1.0, 2.0, 3.0]})
    model.fit(features, target)
    prediction = model.predict(features)
    np.testing.assert_array_equal(
        prediction,
        np.array([20.0, 20.0, 20.0]),
    )
