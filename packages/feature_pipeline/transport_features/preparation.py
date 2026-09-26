from collections.abc import Iterable

import numpy as np
import pandas as pd

POINT_COLUMNS = (
    "sample_id",
    "tr_id",
    "T",
    "target_stop_id",
    "target_time_begin",
    "cur_dev_s",
)

TRAFFIC_COLUMNS = (
    "tr_id",
    "event_time",
    "speed",
    "lon",
    "lat",
)

SCHEDULE_COLUMNS = (
    "tr_id",
    "tt_action_item_id",
    "time_begin",
)


# Проверяет наличие обязательных колонок.
def validate_columns(
    frame: pd.DataFrame,
    required: Iterable[str],
    frame_name: str,
) -> None:
    missing = set(required).difference(frame.columns)
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(f"{frame_name} misses columns: {names}")


# Проверяет уникальность прогнозных точек.
def validate_unique_samples(points: pd.DataFrame) -> None:
    duplicates = int(points["sample_id"].duplicated().sum())
    if duplicates:
        raise ValueError(f"points contains {duplicates} duplicate sample_id")


# Определяет единицу измерения Unix timestamp.
def parse_datetime_series_unit(series: pd.Series) -> str:
    finite = series[np.isfinite(series)]
    if finite.empty:
        return "s"
    median = float(finite.abs().median())
    if median >= 1e17:
        return "ns"
    if median >= 1e14:
        return "us"
    if median >= 1e11:
        return "ms"
    return "s"


# Преобразует временную колонку к UTC datetime.
def parse_datetime_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    numeric_ratio = float(numeric.notna().mean()) if len(series) else 0.0
    if numeric_ratio > 0.95:
        unit = parse_datetime_series_unit(numeric)
        return pd.to_datetime(
            numeric,
            unit=unit,
            utc=True,
            errors="coerce",
        )
    return pd.to_datetime(series, utc=True, errors="coerce")


# Преобразует перечисленные колонки в числовой тип.
def convert_numeric_columns(
    frame: pd.DataFrame,
    columns: Iterable[str],
) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        if column in result:
            result[column] = pd.to_numeric(
                result[column],
                errors="coerce",
            )
    return result


# Преобразует распространённые логические значения.
def convert_boolean_series(series: pd.Series) -> pd.Series:
    mapping = {
        "true": True,
        "false": False,
        "1": True,
        "0": False,
        "yes": True,
        "no": False,
    }
    normalized = series.astype("string").str.strip().str.lower()
    return normalized.map(mapping).fillna(False).astype(bool)


# Подготавливает прогнозные точки.
def prepare_points(points: pd.DataFrame) -> pd.DataFrame:
    validate_columns(points, POINT_COLUMNS, "points")
    result = points.copy()
    result["sample_id"] = result["sample_id"].astype(str)
    result["tr_id"] = result["tr_id"].astype(str)
    result["target_stop_id"] = result["target_stop_id"].astype(str)
    result["T"] = parse_datetime_series(result["T"])
    result["target_time_begin"] = parse_datetime_series(result["target_time_begin"])
    result["cur_dev_s"] = pd.to_numeric(
        result["cur_dev_s"],
        errors="coerce",
    )
    prepare_points_validate(result)
    return result.sort_values(
        ["tr_id", "T"],
        kind="stable",
    ).reset_index(drop=True)


# Проверяет подготовленные прогнозные точки.
def prepare_points_validate(points: pd.DataFrame) -> None:
    validate_unique_samples(points)
    required = ["T", "target_time_begin", "cur_dev_s"]
    if points[required].isna().any().any():
        raise ValueError("points contains invalid time or cur_dev_s values")
    horizons = (points["target_time_begin"] - points["T"]).dt.total_seconds()
    if (horizons <= 0).any():
        raise ValueError("points contains non-positive prediction horizon")


# Подготавливает логические колонки телеметрии.
def prepare_traffic_booleans(
    traffic: pd.DataFrame,
) -> pd.DataFrame:
    result = traffic.copy()
    defaults = {
        "location_valid": False,
        "is_hist_data": False,
    }
    for column, default in defaults.items():
        if column not in result:
            result[column] = default
        else:
            result[column] = convert_boolean_series(result[column])
    return result


# Подготавливает телеметрию.
def prepare_traffic(traffic: pd.DataFrame) -> pd.DataFrame:
    validate_columns(traffic, TRAFFIC_COLUMNS, "traffic")
    result = traffic.copy()
    result["tr_id"] = result["tr_id"].astype(str)
    result["event_time"] = parse_datetime_series(result["event_time"])
    if "receive_time" in result:
        result["receive_time"] = parse_datetime_series(result["receive_time"])
    result = convert_numeric_columns(
        result,
        ["speed", "lon", "lat", "alt", "heading"],
    )
    result = prepare_traffic_booleans(result)
    result = result[result["event_time"].notna()]
    return result.sort_values(
        ["tr_id", "event_time"],
        kind="stable",
    ).reset_index(drop=True)


# Подготавливает расписание.
def prepare_schedule(schedule: pd.DataFrame) -> pd.DataFrame:
    validate_columns(schedule, SCHEDULE_COLUMNS, "schedule")
    result = schedule.copy()
    result["tr_id"] = result["tr_id"].astype(str)
    result["tt_action_item_id"] = result["tt_action_item_id"].astype(str)
    result["time_begin"] = parse_datetime_series(result["time_begin"])
    result = result[result["time_begin"].notna()]
    return result.sort_values(
        ["tr_id", "time_begin"],
        kind="stable",
    ).reset_index(drop=True)
