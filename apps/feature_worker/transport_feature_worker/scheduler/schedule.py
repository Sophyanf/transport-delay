from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class ScheduledStop:
    tr_id: str
    stop_id: str
    planned_time: datetime


class ScheduleRepository:
    # Загружает и индексирует плановое расписание.
    def __init__(self, schedule_path: Path) -> None:
        self._schedule = self._load_schedule(schedule_path)
        self._groups = self._load_schedule_groups(self._schedule)

    # Возвращает копию расписания для FeatureBuilder.
    def frame(self) -> pd.DataFrame:
        return self._schedule.copy()

    # Находит первую остановку в горизонте 10–15 минут.
    def target_stop(
        self,
        tr_id: str,
        current_time: datetime,
    ) -> ScheduledStop | None:
        vehicle = self._groups.get(str(tr_id))
        if vehicle is None or vehicle.empty:
            return None
        lower = pd.Timestamp(current_time) + pd.Timedelta(minutes=10)
        upper = pd.Timestamp(current_time) + pd.Timedelta(minutes=15)
        candidates = vehicle[(vehicle["time_begin"] > lower) & (vehicle["time_begin"] <= upper)]
        if candidates.empty:
            return None
        return self._target_stop_from_row(candidates.iloc[0])

    # Загружает CSV планового расписания.
    def _load_schedule(self, path: Path) -> pd.DataFrame:
        if not path.is_file():
            raise FileNotFoundError(path)
        schedule = pd.read_csv(
            path,
            dtype={
                "tr_id": str,
                "tt_action_item_id": str,
            },
            low_memory=False,
        )
        self._load_schedule_validate(schedule)
        schedule["time_begin"] = pd.to_datetime(
            schedule["time_begin"],
            utc=True,
            errors="coerce",
        )
        schedule = schedule[schedule["time_begin"].notna()]
        return schedule.sort_values(
            ["tr_id", "time_begin"],
            kind="stable",
        ).reset_index(drop=True)

    # Проверяет обязательные колонки расписания.
    def _load_schedule_validate(
        self,
        schedule: pd.DataFrame,
    ) -> None:
        required = {
            "tr_id",
            "tt_action_item_id",
            "time_begin",
        }
        missing = required.difference(schedule.columns)
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(f"Schedule misses columns: {names}")

    # Группирует расписание по транспортным средствам.
    def _load_schedule_groups(
        self,
        schedule: pd.DataFrame,
    ) -> dict[str, pd.DataFrame]:
        return {
            str(tr_id): group.reset_index(drop=True)
            for tr_id, group in schedule.groupby(
                "tr_id",
                sort=False,
            )
        }

    # Преобразует строку расписания в ScheduledStop.
    def _target_stop_from_row(
        self,
        row: pd.Series,
    ) -> ScheduledStop:
        planned_time = row["time_begin"].to_pydatetime()
        return ScheduledStop(
            tr_id=str(row["tr_id"]),
            stop_id=str(row["tt_action_item_id"]),
            planned_time=planned_time,
        )
