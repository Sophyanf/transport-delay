import math
import re
from itertools import pairwise

import numpy as np
import pandas as pd

EARTH_RADIUS_M = 6_371_000.0

POINT_PATTERN = re.compile(
    r"POINT\s*(?:Z\s*)?\(\s*"
    r"(-?\d+(?:\.\d+)?)\s+"
    r"(-?\d+(?:\.\d+)?)"
    r"(?:\s+-?\d+(?:\.\d+)?)?\s*\)",
    re.IGNORECASE,
)


# Возвращает конечный float или NaN.
def finite_float(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return number if np.isfinite(number) else float("nan")


# Извлекает координаты из WKT POINT.
def parse_wkt_point(value: object) -> tuple[float, float]:
    if not isinstance(value, str):
        return float("nan"), float("nan")
    match = POINT_PATTERN.search(value)
    if match is None:
        return float("nan"), float("nan")
    return float(match.group(1)), float(match.group(2))


# Возвращает первое конечное значение указанных колонок.
def extract_stop_coordinates_first(
    row: pd.Series,
    columns: tuple[str, ...],
) -> float:
    for column in columns:
        if column in row:
            value = finite_float(row.get(column))
            if np.isfinite(value):
                return value
    return float("nan")


# Извлекает координаты из отдельных колонок расписания.
def extract_stop_coordinates_explicit(
    row: pd.Series,
) -> tuple[float, float]:
    longitude = extract_stop_coordinates_first(
        row,
        ("lon", "longitude", "stop_lon"),
    )
    latitude = extract_stop_coordinates_first(
        row,
        ("lat", "latitude", "stop_lat"),
    )
    return longitude, latitude


# Извлекает координаты остановки.
def extract_stop_coordinates(
    row: pd.Series,
) -> tuple[float, float]:
    explicit = extract_stop_coordinates_explicit(row)
    if all(np.isfinite(value) for value in explicit):
        return explicit
    return parse_wkt_point(row.get("geom"))


# Вычисляет расстояние между двумя координатами.
def haversine_m(
    longitude_1: float,
    latitude_1: float,
    longitude_2: float,
    latitude_2: float,
) -> float:
    values = (longitude_1, latitude_1, longitude_2, latitude_2)
    if not all(np.isfinite(value) for value in values):
        return float("nan")
    lon_1, lat_1, lon_2, lat_2 = map(math.radians, values)
    delta_lon = lon_2 - lon_1
    delta_lat = lat_2 - lat_1
    haversine = math.sin(delta_lat / 2) ** 2
    haversine += (
        math.cos(lat_1)
        * math.cos(lat_2)
        * math.sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(haversine))


# Отбирает телеметрию с пригодными координатами.
def select_valid_locations(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    result = frame.copy()
    result["lon"] = pd.to_numeric(result["lon"], errors="coerce")
    result["lat"] = pd.to_numeric(result["lat"], errors="coerce")
    mask = result["lon"].between(-180, 180)
    mask &= result["lat"].between(-90, 90)
    if "location_valid" in result:
        mask &= result["location_valid"].fillna(False).astype(bool)
    return result.loc[mask]


# Вычисляет длину GPS-траектории.
def travelled_distance_m(frame: pd.DataFrame) -> float:
    valid = select_valid_locations(frame)
    if valid.empty:
        return float("nan")
    if len(valid) == 1:
        return 0.0
    coordinates = valid[["lon", "lat"]].to_numpy(dtype=float)
    total = 0.0
    for previous, current in pairwise(coordinates):
        total += haversine_m(*previous, *current)
    return float(total)


# Вычисляет расстояние до целевой остановки.
def distance_to_stop_m(
    history: pd.DataFrame,
    stop_coordinates: tuple[float, float],
) -> float:
    valid = select_valid_locations(history)
    if valid.empty:
        return float("nan")
    last = valid.iloc[-1]
    stop_lon, stop_lat = stop_coordinates
    return haversine_m(
        finite_float(last["lon"]),
        finite_float(last["lat"]),
        stop_lon,
        stop_lat,
    )