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
    def __init__(
        self,
        schedule_path: Path,
        daily: bool = True,
    ) -> None:
        self._daily = daily
        self._schedule = self._load_schedule(schedule_path)
        self._groups = self._load_schedule_groups(self._schedule)

    # Возвращает копию расписания для FeatureBuilder.
    def frame(self) -> pd.DataFrame:
        return self._schedule.copy()

    # Находит первую остановку в горизонте 10–15 минут.
    # При daily=True расписание считается ежедневным:
    # дата игнорируется, сравнивается время суток.
    # Возвращаемое planned_time всегда привязано
    # к текущему дню (или следующему после полуночи),
    # чтобы горизонт прогноза был положительным.
    def target_stop(
        self,
        tr_id: str,
        current_time: datetime,
    ) -> ScheduledStop | None:
        vehicle = self._groups.get(str(tr_id).strip())
        if vehicle is None or vehicle.empty:
            return None

        current = pd.Timestamp(current_time)
        if current.tzinfo is None:
            current = current.tz_localize("UTC")
        else:
            current = current.tz_convert("UTC")

        if self._daily:
            planned = self._daily_candidates(vehicle, current)
        else:
            planned = vehicle["time_begin"]

        lower = current + pd.Timedelta(minutes=10)
        upper = current + pd.Timedelta(minutes=15)
        mask = ((planned > lower) & (planned <= upper)).to_numpy()
        if not mask.any():
            return None
        pos = int(mask.argmax())

        row = vehicle.iloc[pos % len(vehicle)]
        return ScheduledStop(
            tr_id=str(row["tr_id"]),
            stop_id=str(row["tt_action_item_id"]),
            planned_time=planned.iloc[pos].to_pydatetime(),
        )

    # Строит абсолютные времена остановок
    # на текущий и следующий день по времени суток.
    def _daily_candidates(
        self,
        vehicle: pd.DataFrame,
        current: pd.Timestamp,
    ) -> pd.Series:
        day_start = current.normalize()
        next_day = day_start + pd.Timedelta(days=1)
        offsets = vehicle["time_begin"] - vehicle["time_begin"].dt.normalize()
        return pd.concat(
            [
                day_start + offsets,
                next_day + offsets,
            ],
            ignore_index=True,
        )

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
        schedule["tr_id"] = schedule["tr_id"].astype(str).str.strip()
        schedule["tt_action_item_id"] = (
            schedule["tt_action_item_id"].astype(str).str.strip()
        )
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
