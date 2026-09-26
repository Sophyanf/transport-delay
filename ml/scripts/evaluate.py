import argparse
from pathlib import Path

import pandas as pd
from transport_ml.io import read_csv_file, read_parquet_file
from transport_ml.metrics import mean_absolute_error
from transport_ml.validation import validate_feature_coverage
from transport_model_core import ModelLoader


# Читает аргументы оценки обученной модели.
def parse_evaluate_arguments() -> argparse.Namespace:
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


# Подготавливает таблицу локальной оценки.
def prepare_evaluate_dataset(
    features: pd.DataFrame,
    labels: pd.DataFrame,
) -> pd.DataFrame:
    validate_feature_coverage(features, labels)
    target_columns = [
        "sample_id",
        "target_delay_s",
        "cur_dev_s",
    ]
    return features.merge(
        labels[target_columns],
        on="sample_id",
        how="inner",
        suffixes=("", "_label"),
        validate="one_to_one",
    )


# Вычисляет MAE модели и baseline.
def execute_evaluate(
    model_root: Path,
    plugin: str,
    version: str,
    dataset: pd.DataFrame,
) -> dict[str, float]:
    model = ModelLoader(model_root).load(plugin, version)
    prediction = model.predict(dataset)
    target = dataset["target_delay_s"].to_numpy(dtype=float)
    baseline_column = execute_evaluate_baseline_column(dataset)
    baseline = dataset[baseline_column].to_numpy(dtype=float)
    return {
        "mae_model": mean_absolute_error(target, prediction),
        "mae_cur_dev": mean_absolute_error(target, baseline),
    }


# Возвращает имя baseline-колонки после объединения.
def execute_evaluate_baseline_column(
    dataset: pd.DataFrame,
) -> str:
    if "cur_dev_s_label" in dataset:
        return "cur_dev_s_label"
    return "cur_dev_s"


# Печатает результаты локальной оценки.
def print_evaluate_metrics(metrics: dict[str, float]) -> None:
    improvement = metrics["mae_cur_dev"] - metrics["mae_model"]
    print(f"mae_model={metrics['mae_model']:.6f}")
    print(f"mae_cur_dev={metrics['mae_cur_dev']:.6f}")
    print(f"improvement={improvement:.6f}")


# Запускает локальную оценку модели.
def main() -> None:
    arguments = parse_evaluate_arguments()
    features = read_parquet_file(arguments.features)
    labels = read_csv_file(arguments.labels)
    dataset = prepare_evaluate_dataset(features, labels)
    metrics = execute_evaluate(
        arguments.model_root,
        arguments.plugin,
        arguments.version,
        dataset,
    )
    print_evaluate_metrics(metrics)


if __name__ == "__main__":
    main()
