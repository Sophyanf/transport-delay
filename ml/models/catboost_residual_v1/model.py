import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from transport_features import create_feature_registry
from transport_model_core import ModelManifest


class CatBoostResidualModel:
    # Создаёт residual CatBoost по манифесту.
    def __init__(
        self,
        manifest: ModelManifest,
        plugin_directory: Path,
    ) -> None:
        self._manifest = manifest
        self._plugin_directory = plugin_directory
        self._artifact_path = plugin_directory / manifest.artifact
        self._metadata_path = self._artifact_path.with_suffix(".json")
        feature_set = create_feature_registry().get(manifest.feature_set)
        self.name = manifest.name
        self.version = manifest.version
        self.feature_names = feature_set.feature_names
        self._model = self._create_regressor()

    # Создаёт CatBoost-регрессор с MAE loss.
    def _create_regressor(self) -> CatBoostRegressor:
        parameters = self._manifest.metadata.get("parameters", {})
        defaults: dict[str, Any] = {
            "loss_function": "MAE",
            "eval_metric": "MAE",
            "iterations": 900,
            "depth": 8,
            "learning_rate": 0.035,
            "l2_leaf_reg": 8.0,
            "random_seed": 42,
            "allow_writing_files": False,
            "verbose": False,
        }
        if isinstance(parameters, dict):
            defaults.update(parameters)
        return CatBoostRegressor(**defaults)

    # Обучает модель на остатке относительно cur_dev_s.
    def fit(
        self,
        features: pd.DataFrame,
        target: pd.Series,
    ) -> None:
        matrix = self._prepare_matrix(features)
        baseline = self._prepare_baseline(features)
        target_values = pd.to_numeric(target, errors="raise").to_numpy(dtype=float)
        residual = target_values - baseline
        self._model.fit(matrix, residual)

    # Возвращает итоговый прогноз задержки.
    def predict(self, features: pd.DataFrame) -> np.ndarray:
        matrix = self._prepare_matrix(features)
        baseline = self._prepare_baseline(features)
        residual = np.asarray(
            self._model.predict(matrix),
            dtype=float,
        )
        return self._clip_predictions(baseline + residual)

    # Загружает CatBoost-артефакт с диска.
    def load(self) -> None:
        if not self._artifact_path.is_file():
            raise FileNotFoundError(self._artifact_path)
        self._model.load_model(str(self._artifact_path))
        self._validate_saved_metadata()

    # Сохраняет модель и описание признаков.
    def save(self) -> None:
        self._artifact_path.parent.mkdir(parents=True, exist_ok=True)
        self._model.save_model(str(self._artifact_path))
        self._save_metadata()

    # Проверяет и упорядочивает признаки.
    def _prepare_matrix(
        self,
        features: pd.DataFrame,
    ) -> pd.DataFrame:
        categorical = self._categorical_names()
        expected = self._expected_feature_names()
        order = list(expected) if expected else list(self.feature_names)
        matrix = pd.DataFrame(index=features.index)
        for column in order:
            if column in features.columns:
                matrix[column] = features[column]
            elif column in categorical:
                matrix[column] = "nan"
            else:
                matrix[column] = np.nan
        for column in matrix.columns:
            series = matrix[column]
            if column in categorical:
                if series.isna().any():
                    matrix[column] = series.map(self._as_category_value)
                elif series.dtype.kind == "f":
                    matrix[column] = series.round().astype("int64")
            else:
                matrix[column] = pd.to_numeric(series, errors="coerce")
        return matrix

    # Возвращает порядок признаков, сохранённый в модели.
    def _expected_feature_names(self) -> list[str]:
        names = getattr(self._model, "feature_names_", None)
        return list(names) if names else []

    # Приводит значение категориального признака к строке.
    @staticmethod
    def _as_category_value(value: Any) -> str:
        if pd.isna(value):
            return "nan"
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    # Определяет категориальные колонки по индексам обученной модели.
    def _categorical_names(self) -> set[str]:
        try:
            indices = self._model.get_cat_feature_indices()
        except Exception:
            return set()
        names = self._expected_feature_names() or list(self.feature_names)
        return {
            names[index]
            for index in indices
            if 0 <= index < len(names)
        }

    # Извлекает текущую задержку как baseline.
    def _prepare_baseline(
        self,
        features: pd.DataFrame,
    ) -> np.ndarray:
        baseline = pd.to_numeric(
            features["cur_dev_s"],
            errors="coerce",
        )
        if baseline.isna().any():
            raise ValueError("cur_dev_s contains invalid values")
        return baseline.to_numpy(dtype=float)

    # Ограничивает прогноз диапазоном из манифеста.
    def _clip_predictions(
        self,
        predictions: np.ndarray,
    ) -> np.ndarray:
        lower = float(self._manifest.metadata.get("clip_lower_s", -900))
        upper = float(self._manifest.metadata.get("clip_upper_s", 1800))
        return np.clip(predictions, lower, upper)

    # Сохраняет метаданные обученного артефакта.
    def _save_metadata(self) -> None:
        payload = {
            "name": self.name,
            "version": self.version,
            "feature_set": self._manifest.feature_set,
            "feature_names": list(self.feature_names),
        }
        self._metadata_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # Проверяет совместимость сохранённых метаданных.
    def _validate_saved_metadata(self) -> None:
        if not self._metadata_path.is_file():
            return
        payload = json.loads(self._metadata_path.read_text(encoding="utf-8"))
        saved_features = tuple(payload.get("feature_names", ()))
        if saved_features and saved_features != self.feature_names:
            raise ValueError("Saved feature order differs from manifest")
