from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from transport_features.geography import (
    distance_to_stop_m,
    extract_stop_coordinates,
    finite_float,
)
from transport_features.preparation import (
    prepare_points,
    prepare_schedule,
    prepare_traffic,
)
from transport_features.schema import FeatureSet, create_feature_registry
from transport_features.windows import build_window_features


@dataclass(frozen=True)
class ScheduleTarget:
    longitude: float
    latitude: float
    sequence: int
    previous_gap_s: float
    next_gap_s: float


class TrafficIndex:
    # Индексирует телеметрию по транспортным средствам.
    def __init__(self, traffic: pd.DataFrame) -> None:
        self._empty = traffic.iloc[0:0].copy()
        self._frames = self._build_traffic_index_frames(traffic)

    # Создаёт отсортированные таблицы телеметрии каждого ТС.
    def _build_traffic_index_frames(
        self,
        traffic: pd.DataFrame,
    ) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        for tr_id, group in traffic.groupby("tr_id", sort=False):
            ordered = group.sort_values(
                "event_time",
                kind="stable",
            )
            frames[str(tr_id)] = ordered.reset_index(drop=True)
        return frames

    # Возвращает телеметрию не позднее момента прогнозирования.
    def history(
        self,
        tr_id: str,
        prediction_time: pd.Timestamp,
    ) -> pd.DataFrame:
        frame = self._frames.get(str(tr_id))
        if frame is None or frame.empty:
            return self._empty.copy()

        timestamp = self._history_timestamp(prediction_time)
        position = int(
            frame["event_time"].searchsorted(
                timestamp,
                side="right",
            )
        )
        return frame.iloc[:position].copy()

    # Приводит момент прогнозирования к часовому поясу UTC.
    def _history_timestamp(
        self,
        prediction_time: pd.Timestamp,
    ) -> pd.Timestamp:
        timestamp = pd.Timestamp(prediction_time)
        if timestamp.tzinfo is None:
            return timestamp.tz_localize("UTC")
        return timestamp.tz_convert("UTC")


class ScheduleIndex:
    # Индексирует целевые остановки расписания.
    def __init__(self, schedule: pd.DataFrame) -> None:
        self._targets: dict[
            tuple[str, str],
            list[tuple[pd.Timestamp, ScheduleTarget]],
        ] = {}
        self._build_schedule_index(schedule)

    # Индексирует расписание отдельно для каждого ТС.
    def _build_schedule_index(
        self,
        schedule: pd.DataFrame,
    ) -> None:
        for _, vehicle in schedule.groupby("tr_id", sort=False):
            self._build_schedule_index_vehicle(vehicle)

    # Добавляет расписание одного ТС в индекс.
    def _build_schedule_index_vehicle(
        self,
        vehicle: pd.DataFrame,
    ) -> None:
        ordered = vehicle.sort_values(
            "time_begin",
            kind="stable",
        ).reset_index(drop=True)

        for position, row in ordered.iterrows():
            key = (
                str(row["tr_id"]),
                str(row["tt_action_item_id"]),
            )
            target = self._build_schedule_index_target(
                ordered,
                position,
            )
            planned_time = pd.Timestamp(row["time_begin"])
            self._targets.setdefault(key, []).append((planned_time, target))

    # Создаёт описание одной целевой остановки.
    def _build_schedule_index_target(
        self,
        schedule: pd.DataFrame,
        position: int,
    ) -> ScheduleTarget:
        row = schedule.iloc[position]
        longitude, latitude = extract_stop_coordinates(row)

        return ScheduleTarget(
            longitude=longitude,
            latitude=latitude,
            sequence=position,
            previous_gap_s=self._build_schedule_index_gap(
                schedule,
                position - 1,
                position,
            ),
            next_gap_s=self._build_schedule_index_gap(
                schedule,
                position,
                position + 1,
            ),
        )

    # Вычисляет плановый интервал между остановками.
    def _build_schedule_index_gap(
        self,
        schedule: pd.DataFrame,
        left_position: int,
        right_position: int,
    ) -> float:
        if left_position < 0 or right_position >= len(schedule):
            return float("nan")

        left_time = schedule.iloc[left_position]["time_begin"]
        right_time = schedule.iloc[right_position]["time_begin"]
        return float((right_time - left_time).total_seconds())

    # Находит остановку, ближайшую к целевому плановому времени.
    def find(
        self,
        tr_id: str,
        stop_id: str,
        target_time: pd.Timestamp,
    ) -> ScheduleTarget | None:
        candidates = self._targets.get(
            (str(tr_id), str(stop_id)),
            [],
        )
        if not candidates:
            return None

        timestamp = self._find_timestamp(target_time)
        selected = min(
            candidates,
            key=lambda candidate: abs((candidate[0] - timestamp).total_seconds()),
        )
        return selected[1]

    # Приводит целевое плановое время к UTC.
    def _find_timestamp(
        self,
        target_time: pd.Timestamp,
    ) -> pd.Timestamp:
        timestamp = pd.Timestamp(target_time)
        if timestamp.tzinfo is None:
            return timestamp.tz_localize("UTC")
        return timestamp.tz_convert("UTC")


class FeatureBuilder:
    # Создаёт построитель выбранного набора признаков.
    def __init__(
        self,
        feature_set_name: str = "feature_set_v1",
    ) -> None:
        registry = create_feature_registry()
        self._feature_set = registry.get(feature_set_name)

    # Строит признаки для всех прогнозных точек.
    def build(
        self,
        points: pd.DataFrame,
        traffic: pd.DataFrame,
        schedule: pd.DataFrame,
    ) -> pd.DataFrame:
        prepared_points = prepare_points(points)
        prepared_traffic = prepare_traffic(traffic)
        prepared_schedule = prepare_schedule(schedule)

        traffic_index = TrafficIndex(prepared_traffic)
        schedule_index = ScheduleIndex(prepared_schedule)

        rows = self._build_rows(
            prepared_points,
            traffic_index,
            schedule_index,
        )
        return self._build_select_result(pd.DataFrame(rows))

    # Строит строки признаков для прогнозных точек.
    def _build_rows(
        self,
        points: pd.DataFrame,
        traffic_index: TrafficIndex,
        schedule_index: ScheduleIndex,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []

        for point in points.itertuples(index=False):
            history = traffic_index.history(
                str(point.tr_id),
                point.T,
            )
            target = schedule_index.find(
                str(point.tr_id),
                str(point.target_stop_id),
                point.target_time_begin,
            )
            rows.append(
                self._build_point_features(
                    point,
                    history,
                    target,
                )
            )

        return rows

    # Собирает признаки одной точки без будущей телеметрии.
    def _build_point_features(
        self,
        point: Any,
        history: pd.DataFrame,
        target: ScheduleTarget | None,
    ) -> dict[str, Any]:
        safe_history = self._build_point_features_history(
            history,
            point.T,
        )

        row = self._build_base_features(point)
        row.update(
            self._build_last_features(
                point,
                safe_history,
            )
        )
        row.update(
            build_window_features(
                safe_history,
                point.T,
            )
        )
        row.update(
            self._build_target_features(
                point,
                safe_history,
                target,
            )
        )
        return row

    # Повторно исключает телеметрию после момента прогноза.
    def _build_point_features_history(
        self,
        history: pd.DataFrame,
        prediction_time: pd.Timestamp,
    ) -> pd.DataFrame:
        if history.empty or "event_time" not in history:
            return history.copy()

        event_time = pd.to_datetime(
            history["event_time"],
            utc=True,
            errors="coerce",
        )
        timestamp = self._build_point_features_timestamp(prediction_time)
        mask = event_time.notna() & (event_time <= timestamp)
        return history.loc[mask].copy()

    # Приводит момент прогнозирования к UTC.
    def _build_point_features_timestamp(
        self,
        prediction_time: pd.Timestamp,
    ) -> pd.Timestamp:
        timestamp = pd.Timestamp(prediction_time)
        if timestamp.tzinfo is None:
            return timestamp.tz_localize("UTC")
        return timestamp.tz_convert("UTC")

    # Вычисляет базовые признаки прогнозной точки.
    def _build_base_features(
        self,
        point: Any,
    ) -> dict[str, Any]:
        horizon = (point.target_time_begin - point.T).total_seconds()
        midnight = point.T.normalize()
        seconds_from_midnight = (point.T - midnight).total_seconds()

        return {
            "sample_id": str(point.sample_id),
            "tr_id": str(point.tr_id),
            "target_stop_id": str(point.target_stop_id),
            "cur_dev_s": float(point.cur_dev_s),
            "horizon_s": float(horizon),
            "hour": int(point.T.hour),
            "minute": int(point.T.minute),
            "day_of_week": int(point.T.dayofweek),
            "is_weekend": int(point.T.dayofweek >= 5),
            "seconds_from_midnight": float(seconds_from_midnight),
        }

    # Вычисляет признаки последнего доступного пакета.
    def _build_last_features(
        self,
        point: Any,
        history: pd.DataFrame,
    ) -> dict[str, float]:
        if history.empty:
            return self._build_last_features_empty()

        last = history.iloc[-1]
        age = (point.T - last["event_time"]).total_seconds()

        return {
            "telemetry_age_s": float(age),
            "last_speed": finite_float(last.get("speed")),
            "last_heading": finite_float(last.get("heading")),
            "last_altitude": finite_float(last.get("alt")),
            "last_location_valid": float(bool(last.get("location_valid", False))),
            "last_is_historical": float(bool(last.get("is_hist_data", False))),
            "last_receive_lag_s": self._build_last_receive_lag(last),
            "last_lon": finite_float(last.get("lon")),
            "last_lat": finite_float(last.get("lat")),
        }

    # Возвращает пустые признаки последнего пакета.
    def _build_last_features_empty(self) -> dict[str, float]:
        names = (
            "telemetry_age_s",
            "last_speed",
            "last_heading",
            "last_altitude",
            "last_location_valid",
            "last_is_historical",
            "last_receive_lag_s",
            "last_lon",
            "last_lat",
        )
        return {name: float("nan") for name in names}

    # Вычисляет задержку доставки последнего пакета.
    def _build_last_receive_lag(
        self,
        row: pd.Series,
    ) -> float:
        receive_time = row.get("receive_time")
        event_time = row.get("event_time")

        if pd.isna(receive_time) or pd.isna(event_time):
            return float("nan")

        difference = receive_time - event_time
        return float(difference.total_seconds())

    # Вычисляет признаки целевой остановки.
    def _build_target_features(
        self,
        point: Any,
        history: pd.DataFrame,
        target: ScheduleTarget | None,
    ) -> dict[str, float]:
        if target is None:
            return self._build_target_features_empty()

        distance = distance_to_stop_m(
            history,
            (target.longitude, target.latitude),
        )
        horizon = float((point.target_time_begin - point.T).total_seconds())
        required_speed = self._build_target_required_speed(
            distance,
            horizon,
        )
        current_speed = self._build_target_last_speed(history)

        return self._build_target_features_result(
            target,
            distance,
            horizon,
            current_speed,
            required_speed,
        )

    # Собирает результат признаков целевой остановки.
    def _build_target_features_result(
        self,
        target: ScheduleTarget,
        distance: float,
        horizon: float,
        current_speed: float,
        required_speed: float,
    ) -> dict[str, float]:
        return {
            "distance_to_target_m": distance,
            "required_speed_kmh": required_speed,
            "speed_to_required_ratio": (
                self._build_target_speed_ratio(
                    current_speed,
                    required_speed,
                )
            ),
            "eta_delay_s": self._build_target_eta_delay(
                distance,
                current_speed,
                horizon,
            ),
            "previous_stop_gap_s": target.previous_gap_s,
            "next_stop_gap_s": target.next_gap_s,
            "target_stop_sequence": float(target.sequence),
        }

    # Возвращает пустые признаки целевой остановки.
    def _build_target_features_empty(self) -> dict[str, float]:
        names = (
            "distance_to_target_m",
            "required_speed_kmh",
            "speed_to_required_ratio",
            "eta_delay_s",
            "previous_stop_gap_s",
            "next_stop_gap_s",
            "target_stop_sequence",
        )
        return {name: float("nan") for name in names}

    # Вычисляет необходимую скорость до остановки.
    def _build_target_required_speed(
        self,
        distance_m: float,
        horizon_s: float,
    ) -> float:
        if not np.isfinite(distance_m) or horizon_s <= 0:
            return float("nan")
        return float(distance_m / horizon_s * 3.6)

    # Возвращает последнюю доступную скорость ТС.
    def _build_target_last_speed(
        self,
        history: pd.DataFrame,
    ) -> float:
        if history.empty or "speed" not in history:
            return float("nan")

        speeds = pd.to_numeric(
            history["speed"],
            errors="coerce",
        ).dropna()

        if speeds.empty:
            return float("nan")

        return float(speeds.iloc[-1])

    # Вычисляет отношение текущей скорости к необходимой.
    def _build_target_speed_ratio(
        self,
        current_speed: float,
        required_speed: float,
    ) -> float:
        if not np.isfinite(current_speed):
            return float("nan")
        if not np.isfinite(required_speed):
            return float("nan")
        return float(current_speed / max(required_speed, 0.1))

    # Оценивает отклонение расчётного ETA от плана.
    def _build_target_eta_delay(
        self,
        distance_m: float,
        current_speed: float,
        horizon_s: float,
    ) -> float:
        values = (
            distance_m,
            current_speed,
            horizon_s,
        )
        if not all(np.isfinite(value) for value in values):
            return float("nan")

        effective_speed = max(current_speed, 3.0)
        speed_mps = effective_speed / 3.6
        travel_time_s = distance_m / speed_mps

        return float(travel_time_s - horizon_s)

    # Выбирает идентификатор, признаки модели и координаты.
    def _build_select_result(
        self,
        frame: pd.DataFrame,
    ) -> pd.DataFrame:
        self._build_select_result_validate(
            frame,
            self._feature_set,
        )

        columns = [
            "sample_id",
            *self._feature_set.feature_names,
            "last_lon",
            "last_lat",
        ]
        return frame.loc[:, columns].copy()

    # Проверяет наличие всех обязательных признаков.
    def _build_select_result_validate(
        self,
        frame: pd.DataFrame,
        feature_set: FeatureSet,
    ) -> None:
        missing = set(feature_set.feature_names).difference(frame.columns)

        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(f"Feature builder misses columns: {names}")


# Строит признаки стандартным FeatureBuilder.
def build_features(
    points: pd.DataFrame,
    traffic: pd.DataFrame,
    schedule: pd.DataFrame,
    feature_set_name: str = "feature_set_v1",
) -> pd.DataFrame:
    builder = FeatureBuilder(feature_set_name)
    return builder.build(
        points,
        traffic,
        schedule,
    )
