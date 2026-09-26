import argparse
from pathlib import Path

import pandas as pd
from transport_features import build_features
from transport_ml.io import read_csv_file, write_parquet_file
from transport_ml.validation import validate_unique_identifier


# Читает аргументы построения признаков.
def parse_build_features_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--points", type=Path, required=True)
    parser.add_argument("--traffic", type=Path, required=True)
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--feature-set", default="feature_set_v1")
    return parser.parse_args()


# Загружает исходные таблицы признакового контура.
def load_build_features_inputs(
    points_path: Path,
    traffic_path: Path,
    schedule_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    points = read_csv_file(points_path)
    traffic = read_csv_file(traffic_path)
    schedule = read_csv_file(schedule_path)
    validate_unique_identifier(points, "sample_id", "points")
    return points, traffic, schedule


# Строит и сохраняет таблицу признаков.
def execute_build_features(
    points_path: Path,
    traffic_path: Path,
    schedule_path: Path,
    output_path: Path,
    feature_set: str,
) -> None:
    points, traffic, schedule = load_build_features_inputs(
        points_path,
        traffic_path,
        schedule_path,
    )
    features = build_features(
        points,
        traffic,
        schedule,
        feature_set,
    )
    write_parquet_file(features, output_path)


# Запускает построение признаков.
def main() -> None:
    arguments = parse_build_features_arguments()
    execute_build_features(
        arguments.points,
        arguments.traffic,
        arguments.schedule,
        arguments.output,
        arguments.feature_set,
    )
    print(arguments.output)


if __name__ == "__main__":
    main()
