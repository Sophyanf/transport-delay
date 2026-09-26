import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from transport_ml.io import read_parquet_file, write_parquet_file
from transport_ml.validation import validate_unique_identifier
from transport_model_core import ModelLoader


# Читает аргументы прогнозирования validate.
def parse_predict_validate_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plugin", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--model-root",
        type=Path,
        default=Path("ml/models"),
    )
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


# Создаёт таблицу прогнозов validate.
def execute_predict_validate(
    model_root: Path,
    plugin: str,
    version: str,
    features: pd.DataFrame,
) -> pd.DataFrame:
    validate_unique_identifier(features, "sample_id", "features")
    model = ModelLoader(model_root).load(plugin, version)
    predictions = np.asarray(
        model.predict(features),
        dtype=float,
    )
    execute_predict_validate_values(predictions, len(features))
    return pd.DataFrame(
        {
            "sample_id": features["sample_id"].astype(str),
            "prediction": predictions,
        }
    )


# Проверяет количество и конечность прогнозов.
def execute_predict_validate_values(
    predictions: np.ndarray,
    expected_length: int,
) -> None:
    if len(predictions) != expected_length:
        raise ValueError("Prediction count differs from feature count")
    if not np.isfinite(predictions).all():
        raise ValueError("Predictions contain non-finite values")


# Запускает прогнозирование validate.
def main() -> None:
    arguments = parse_predict_validate_arguments()
    features = read_parquet_file(arguments.features)
    predictions = execute_predict_validate(
        arguments.model_root,
        arguments.plugin,
        arguments.version,
        features,
    )
    write_parquet_file(predictions, arguments.output)
    print(arguments.output)


if __name__ == "__main__":
    main()
