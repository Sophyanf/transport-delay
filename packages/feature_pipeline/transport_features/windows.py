import numpy as np
import pandas as pd

from transport_features.geography import travelled_distance_m


# Отбирает телеметрию заданного временного окна.
def select_time_window(
    history: pd.DataFrame,
    prediction_time: pd.Timestamp,
    seconds: int,
) -> pd.DataFrame:
    if history.empty:
        return history.copy()
    start = prediction_time - pd.Timedelta(seconds=seconds)
    return history.loc[history["event_time"] >= start]


# Возвращает числовой ряд без пропусков.
def numeric_series(
    frame: pd.DataFrame,
    column: str,
) -> pd.Series:
    if column not in frame:
        return pd.Series(dtype=float)
    return pd.to_numeric(
        frame[column],
        errors="coerce",
    ).dropna()


# Вычисляет безопасную статистику ряда.
def safe_statistic(
    values: pd.Series,
    operation: str,
) -> float:
    if values.empty:
        return float("nan")
    result = getattr(values, operation)()
    return float(result) if pd.notna(result) else float("nan")


# Вычисляет среднюю скорость окна.
def speed_mean(frame: pd.DataFrame) -> float:
    return safe_statistic(
        numeric_series(frame, "speed"),
        "mean",
    )


# Вычисляет изменение скорости в окне.
def speed_change(frame: pd.DataFrame) -> float:
    values = numeric_series(frame, "speed")
    if len(values) < 2:
        return float("nan")
    return float(values.iloc[-1] - values.iloc[0])


# Вычисляет линейный тренд скорости за минуту.
def speed_trend_per_minute(frame: pd.DataFrame) -> float:
    if len(frame) < 2:
        return float("nan")
    speeds = pd.to_numeric(frame["speed"], errors="coerce")
    origin = frame["event_time"].iloc[0]
    seconds = (frame["event_time"] - origin).dt.total_seconds()
    valid = speeds.notna() & seconds.notna()
    if valid.sum() < 2 or seconds.loc[valid].nunique() < 2:
        return float("nan")
    slope = np.polyfit(
        seconds.loc[valid],
        speeds.loc[valid],
        1,
    )[0]
    return float(slope * 60.0)


# Вычисляет долю сообщений со скоростью менее 1 км/ч.
def stopped_ratio(frame: pd.DataFrame) -> float:
    values = numeric_series(frame, "speed")
    if values.empty:
        return float("nan")
    return float((values < 1.0).mean())


# Вычисляет долю сообщений с невалидными координатами.
def invalid_location_ratio(frame: pd.DataFrame) -> float:
    if frame.empty or "location_valid" not in frame:
        return float("nan")
    valid = frame["location_valid"].fillna(False).astype(bool)
    return float((~valid).mean())


# Вычисляет долю исторических пакетов.
def historical_packet_ratio(frame: pd.DataFrame) -> float:
    if frame.empty or "is_hist_data" not in frame:
        return float("nan")
    values = frame["is_hist_data"].fillna(False).astype(bool)
    return float(values.mean())


# Вычисляет среднюю задержку доставки пакетов.
def receive_lag_mean_s(frame: pd.DataFrame) -> float:
    if frame.empty or "receive_time" not in frame:
        return float("nan")
    receive_time = pd.to_datetime(
        frame["receive_time"],
        utc=True,
        errors="coerce",
    )
    event_time = pd.to_datetime(
        frame["event_time"],
        utc=True,
        errors="coerce",
    )
    lag = (receive_time - event_time).dt.total_seconds().dropna()
    return float(lag.mean()) if not lag.empty else float("nan")


# Вычисляет максимальный разрыв между пакетами.
def max_packet_gap_s(frame: pd.DataFrame) -> float:
    if len(frame) < 2:
        return float("nan")
    gaps = frame["event_time"].sort_values().diff().dt.total_seconds().dropna()
    return float(gaps.max()) if not gaps.empty else float("nan")


# Вычисляет среднюю GPS-скорость по траектории.
def coordinate_speed_kmh(frame: pd.DataFrame) -> float:
    if len(frame) < 2:
        return float("nan")
    distance = travelled_distance_m(frame)
    duration = (frame["event_time"].iloc[-1] - frame["event_time"].iloc[0]).total_seconds()
    if not np.isfinite(distance) or duration <= 0:
        return float("nan")
    return float(distance / duration * 3.6)


# Вычисляет базовые показатели окна.
def build_window_basic(
    frame: pd.DataFrame,
    suffix: str,
) -> dict[str, float]:
    return {
        f"packet_count_{suffix}": float(len(frame)),
        f"speed_mean_{suffix}": speed_mean(frame),
    }


# Вычисляет расширенные показатели окна 5 минут.
def build_window_five_minutes(
    frame: pd.DataFrame,
) -> dict[str, float]:
    speeds = numeric_series(frame, "speed")
    return {
        "speed_median_5m": safe_statistic(speeds, "median"),
        "speed_min_5m": safe_statistic(speeds, "min"),
        "speed_max_5m": safe_statistic(speeds, "max"),
        "speed_std_5m": safe_statistic(speeds, "std"),
        "speed_trend_5m": speed_trend_per_minute(frame),
        "stopped_ratio_5m": stopped_ratio(frame),
        "invalid_location_ratio_5m": invalid_location_ratio(frame),
        "historical_packet_ratio_5m": historical_packet_ratio(frame),
        "receive_lag_mean_5m": receive_lag_mean_s(frame),
        "max_packet_gap_5m": max_packet_gap_s(frame),
        "distance_travelled_5m": travelled_distance_m(frame),
        "coordinate_speed_5m": coordinate_speed_kmh(frame),
    }


# Вычисляет изменения для коротких временных окон.
def build_window_features_changes(
    windows: dict[str, pd.DataFrame],
) -> dict[str, float]:
    return {
        "speed_change_1m": speed_change(windows["1m"]),
        "speed_change_3m": speed_change(windows["3m"]),
        "stopped_ratio_1m": stopped_ratio(windows["1m"]),
    }


# Вычисляет все оконные признаки.
def build_window_features(
    history: pd.DataFrame,
    prediction_time: pd.Timestamp,
) -> dict[str, float]:
    windows = {
        "1m": select_time_window(history, prediction_time, 60),
        "3m": select_time_window(history, prediction_time, 180),
        "5m": select_time_window(history, prediction_time, 300),
        "10m": select_time_window(history, prediction_time, 600),
        "15m": select_time_window(history, prediction_time, 900),
    }
    result: dict[str, float] = {}
    for suffix, frame in windows.items():
        result.update(build_window_basic(frame, suffix))
    result.update(build_window_features_changes(windows))
    result.update(build_window_five_minutes(windows["5m"]))
    return result
