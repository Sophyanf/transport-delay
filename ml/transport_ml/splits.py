from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class TimeSplit:
    train_indices: pd.Index
    validation_indices: pd.Index


# Создаёт временное разбиение без перемешивания строк.
def create_time_split(
    frame: pd.DataFrame,
    time_column: str,
    validation_fraction: float = 0.2,
) -> TimeSplit:
    create_time_split_validate(frame, time_column, validation_fraction)
    ordered = frame.sort_values(time_column, kind="stable")
    boundary = max(1, int(len(ordered) * (1 - validation_fraction)))
    train_indices = ordered.index[:boundary]
    validation_indices = ordered.index[boundary:]
    return TimeSplit(
        train_indices=train_indices,
        validation_indices=validation_indices,
    )


# Проверяет параметры временного разбиения.
def create_time_split_validate(
    frame: pd.DataFrame,
    time_column: str,
    validation_fraction: float,
) -> None:
    if time_column not in frame:
        raise ValueError(f"Frame misses time column: {time_column}")
    if len(frame) < 2:
        raise ValueError("At least two rows are required")
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between 0 and 1")
