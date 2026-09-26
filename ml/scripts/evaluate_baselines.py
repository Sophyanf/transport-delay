import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from transport_ml.io import read_csv_file
from transport_ml.metrics import mean_absolute_error


# Читает аргументы оценки базовых прогнозов.
def parse_evaluate_baselines_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-labels", type=Path, required=True)
    parser.add_argument("--test-labels", type=Path, required=True)
    return parser.parse_args()


# Проверяет обязательные колонки разметки.
def evaluate_baselines_validate(labels: pd.DataFrame) -> None:
    required = {"target_delay_s", "cur_dev_s"}
    missing = required.difference(labels.columns)
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(f"Labels miss columns: {names}")


# Вычисляет MAE нулевого и cur_dev_s baseline.
def evaluate_baselines(
    labels: pd.DataFrame,
) -> dict[str, float | int]:
    evaluate_baselines_validate(labels)
    target = pd.to_numeric(
        labels["target_delay_s"],
        errors="raise",
    ).to_numpy(dtype=float)
    current = pd.to_numeric(
        labels["cur_dev_s"],
        errors="raise",
    ).to_numpy(dtype=float)
    return {
        "samples": len(labels),
        "mae_zero": mean_absolute_error(target, np.zeros_like(target)),
        "mae_cur_dev": mean_absolute_error(target, current),
    }


# Печатает метрики одного периода.
def print_evaluate_baselines(
    period: str,
    metrics: dict[str, float | int],
) -> None:
    print(f"[{period}]")
    print(f"samples={metrics['samples']}")
    print(f"mae_zero={metrics['mae_zero']:.6f}")
    print(f"mae_cur_dev={metrics['mae_cur_dev']:.6f}")


# Запускает оценку baseline для train и test.
def main() -> None:
    arguments = parse_evaluate_baselines_arguments()
    train = evaluate_baselines(read_csv_file(arguments.train_labels))
    test = evaluate_baselines(read_csv_file(arguments.test_labels))
    print_evaluate_baselines("train", train)
    print_evaluate_baselines("test", test)


if __name__ == "__main__":
    main()
