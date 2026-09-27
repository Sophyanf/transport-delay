from pathlib import Path
from typing import Any

import pandas as pd


class ScheduleContextRepository:
    # Загружает расписание для определения участка маршрута.
    def __init__(self, schedule_path: Path) -> None:
        self._schedule = self._load_schedule(schedule_path)

    # Возвращает контекст целевой остановки.
    def context(
        self,
        tr_id: str,
        target_stop_id: str,
        target_time_begin: str | None,
    ) -> dict[str, Any]:
        vehicle = self._schedule[self._schedule["tr_id"] == str(tr_id)].reset_index(drop=True)
        if vehicle.empty:
            return self._empty_context()
        position = self._find_position(
            vehicle,
            target_stop_id,
            target_time_begin,
        )
        if position is None:
            return self._empty_context()
        return self._build_context(vehicle, position)

    # Загружает и нормализует расписание.
    def _load_schedule(self, path: Path) -> pd.DataFrame:
        columns = [
            "tr_id",
            "tt_action_item_id",
            "time_begin",
            "building_address",
        ]
        if not path.is_file():
            return pd.DataFrame(columns=columns)
        frame = pd.read_csv(
            path,
            dtype={"tr_id": str, "tt_action_item_id": str},
            low_memory=False,
        )
        frame["time_begin"] = pd.to_datetime(
            frame["time_begin"],
            utc=True,
            errors="coerce",
        )
        if "building_address" not in frame:
            frame["building_address"] = frame["tt_action_item_id"]
        return frame.sort_values(
            ["tr_id", "time_begin"],
            kind="stable",
        ).reset_index(drop=True)

    # Находит позицию целевой остановки.
    def _find_position(
        self,
        vehicle: pd.DataFrame,
        stop_id: str,
        target_time: str | None,
    ) -> int | None:
        candidates = vehicle[vehicle["tt_action_item_id"] == str(stop_id)]
        if candidates.empty:
            return None
        if target_time is None:
            return int(candidates.index[0])
        target = pd.to_datetime(target_time, utc=True, errors="coerce")
        differences = (candidates["time_begin"] - target).abs()
        return int(differences.idxmin())

    # Формирует маршрутный контекст остановки.
    def _build_context(
        self,
        vehicle: pd.DataFrame,
        position: int,
    ) -> dict[str, Any]:
        current = vehicle.loc[position]
        previous = vehicle.loc[position - 1] if position > 0 else None
        next_row = vehicle.loc[position + 1] if position + 1 < len(vehicle) else None
        return {
            "route": None,
            "vehicle_number": None,
            "segment_from": self._stop_name(previous),
            "segment_to": self._stop_name(current),
            "next_stop": self._stop_name(next_row),
        }

    # Возвращает отображаемое имя остановки.
    def _stop_name(self, row: pd.Series | None) -> str | None:
        if row is None:
            return None
        address = row.get("building_address")
        if pd.notna(address) and str(address).strip():
            return str(address)
        return str(row["tt_action_item_id"])

    # Возвращает пустой маршрутный контекст.
    def _empty_context(self) -> dict[str, Any]:
        return {
            "route": None,
            "vehicle_number": None,
            "segment_from": None,
            "segment_to": None,
            "next_stop": None,
        }
