from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from transport_feature_worker.scheduler import ScheduleRepository


# Создаёт тестовый файл расписания.
def create_schedule_file(path: Path) -> None:
    pd.DataFrame(
        {
            "tr_id": [
                "vehicle-1",
                "vehicle-1",
                "vehicle-1",
                "vehicle-2",
            ],
            "tt_action_item_id": [
                "stop-9",
                "stop-12",
                "stop-14",
                "other-stop",
            ],
            "time_begin": [
                "2025-01-01T10:09:00Z",
                "2025-01-01T10:12:00Z",
                "2025-01-01T10:14:00Z",
                "2025-01-01T10:12:00Z",
            ],
            "geom": [
                "POINT (37.1 55.1)",
                "POINT (37.2 55.2)",
                "POINT (37.3 55.3)",
                "POINT (37.4 55.4)",
            ],
        }
    ).to_csv(path, index=False)


# Проверяет выбор первой остановки в горизонте 10–15 минут.
def test_schedule_selects_first_target_in_window(
    tmp_path: Path,
) -> None:
    path = tmp_path / "schedule.csv"
    create_schedule_file(path)
    repository = ScheduleRepository(path)
    current_time = datetime(2025, 1, 1, 10, 0, tzinfo=UTC)
    target = repository.target_stop("vehicle-1", current_time)
    assert target is not None
    assert target.stop_id == "stop-12"
    assert target.planned_time.minute == 12


# Проверяет отсутствие остановки вне требуемого горизонта.
def test_schedule_returns_none_without_target(
    tmp_path: Path,
) -> None:
    path = tmp_path / "schedule.csv"
    create_schedule_file(path)
    repository = ScheduleRepository(path)
    current_time = datetime(2025, 1, 1, 11, 0, tzinfo=UTC)
    assert repository.target_stop("vehicle-1", current_time) is None


# Проверяет строгое исключение границы десяти минут.
def test_schedule_excludes_exact_ten_minutes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "schedule.csv"
    create_schedule_file(path)
    repository = ScheduleRepository(path)
    current_time = datetime(2025, 1, 1, 9, 59, tzinfo=UTC)
    target = repository.target_stop("vehicle-1", current_time)
    assert target is not None
    assert target.stop_id == "stop-12"
