import argparse
from pathlib import Path

import pandas as pd
from transport_ml.io import read_csv_file, read_parquet_file
from transport_ml.validation import validate_feature_coverage
from transport_model_core import ModelLoader


# Читает аргументы обучения модели.
def parse_train_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plugin", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--model-root",
        type=Path,
        default=Path("ml/models"),
    )
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    return parser.parse_args()


# Объединяет признаки с целевой переменной.
def prepare_train_dataset(
    features: pd.DataFrame,
    labels: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series]:
    validate_feature_coverage(features, labels)
    target_frame = labels[["sample_id", "target_delay_s"]].copy()
    merged = features.merge(
        target_frame,
        on="sample_id",
        how="inner",
        validate="one_to_one",
    )
    target = pd.to_numeric(
        merged.pop("target_delay_s"),
        errors="raise",
    )
    return merged, target


# Обучает и сохраняет выбранный модельный плагин.
def execute_train(
    model_root: Path,
    plugin: str,
    version: str,
    features: pd.DataFrame,
    target: pd.Series,
) -> None:
    loader = ModelLoader(model_root)
    model = loader.create(plugin, version)
    model.fit(features, target)
    model.save()


# Запускает обучение модели.
def main() -> None:
    arguments = parse_train_arguments()
    features = read_parquet_file(arguments.features)
    labels = read_csv_file(arguments.labels)
    matrix, target = prepare_train_dataset(features, labels)
    execute_train(
        arguments.model_root,
        arguments.plugin,
        arguments.version,
        matrix,
        target,
    )
    print(f"{arguments.plugin}:{arguments.version}")


if __name__ == "__main__":
    main()
