import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
from transport_ml.io import read_csv_file

DATASET_FILES = {
    "train_traffic": "train/traffic.csv",
    "train_schedule": "train/schedule.csv",
    "test_traffic": "test/traffic.csv",
    "test_schedule": "test/schedule.csv",
    "validate_traffic": "validate/traffic.csv",
    "validate_schedule": "validate/schedule_plan.csv",
    "validate_points": "validate/points.csv",
    "train_labels": "labels/labels_train.csv",
    "test_labels": "labels/labels_test.csv",
    "submission": "sample_submission.csv",
}


# Читает аргументы аудита датасета.
def parse_audit_data_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/interim/audit_report.json"),
    )
    return parser.parse_args()


# Возвращает разделитель конкретного файла.
def audit_data_separator(name: str) -> str:
    return ";" if name == "submission" else ","


# Собирает статистику одной таблицы.
def audit_data_frame(
    name: str,
    frame: pd.DataFrame,
    path: Path,
) -> dict[str, Any]:
    return {
        "name": name,
        "path": str(path),
        "rows": len(frame),
        "columns": frame.columns.tolist(),
        "missing": audit_data_missing(frame),
        "duplicates": int(frame.duplicated().sum()),
        "memory_mb": round(
            float(frame.memory_usage(deep=True).sum()) / 1_048_576,
            3,
        ),
        "time_ranges": audit_data_time_ranges(frame),
        "identifier_counts": audit_data_identifier_counts(frame),
    }


# Вычисляет количество пропусков по колонкам.
def audit_data_missing(frame: pd.DataFrame) -> dict[str, int]:
    return {
        str(column): int(count) for column, count in frame.isna().sum().items() if int(count) > 0
    }


# Вычисляет диапазоны известных временных колонок.
def audit_data_time_ranges(
    frame: pd.DataFrame,
) -> dict[str, dict[str, str | None]]:
    columns = ("event_time", "T", "target_time_begin", "time_begin")
    result: dict[str, dict[str, str | None]] = {}
    for column in columns:
        if column in frame:
            result[column] = audit_data_time_range(frame[column])
    return result


# Вычисляет диапазон одной временной колонки.
def audit_data_time_range(
    series: pd.Series,
) -> dict[str, str | None]:
    values = pd.to_datetime(series, utc=True, errors="coerce").dropna()
    if values.empty:
        return {"minimum": None, "maximum": None}
    return {
        "minimum": values.min().isoformat(),
        "maximum": values.max().isoformat(),
    }


# Считает уникальные значения основных идентификаторов.
def audit_data_identifier_counts(
    frame: pd.DataFrame,
) -> dict[str, int]:
    columns = ("sample_id", "tr_id", "target_stop_id", "unit_id")
    return {
        column: int(frame[column].nunique(dropna=True)) for column in columns if column in frame
    }


# Проверяет горизонт прогнозных точек.
def audit_data_horizon(
    frame: pd.DataFrame,
) -> dict[str, float | int] | None:
    required = {"T", "target_time_begin"}
    if not required.issubset(frame.columns):
        return None
    current = pd.to_datetime(frame["T"], utc=True, errors="coerce")
    target = pd.to_datetime(
        frame["target_time_begin"],
        utc=True,
        errors="coerce",
    )
    horizon = (target - current).dt.total_seconds().dropna()
    if horizon.empty:
        return None
    return {
        "minimum_s": float(horizon.min()),
        "maximum_s": float(horizon.max()),
        "outside_competition_window": int(((horizon <= 600) | (horizon > 900)).sum()),
    }


# Выполняет аудит всех файлов раздачи.
def execute_audit_data(data_root: Path) -> dict[str, Any]:
    report: dict[str, Any] = {"files": {}, "horizons": {}}
    for name, relative_path in DATASET_FILES.items():
        path = data_root / relative_path
        separator = audit_data_separator(name)
        frame = read_csv_file(path, separator)
        report["files"][name] = audit_data_frame(name, frame, path)
        horizon = audit_data_horizon(frame)
        if horizon is not None:
            report["horizons"][name] = horizon
    return report


# Сохраняет отчёт аудита в JSON.
def save_audit_data_report(
    report: dict[str, Any],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# Запускает аудит датасета.
def main() -> None:
    arguments = parse_audit_data_arguments()
    report = execute_audit_data(arguments.data_root)
    save_audit_data_report(report, arguments.output)
    print(arguments.output)


if __name__ == "__main__":
    main()
