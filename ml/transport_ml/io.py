from pathlib import Path

import pandas as pd

IDENTIFIER_COLUMNS = {
    "sample_id": "string",
    "tr_id": "string",
    "target_stop_id": "string",
    "tt_action_item_id": "string",
    "unit_id": "string",
    "packet_id": "string",
    "device_event_id": "string",
}


# Возвращает типы известных идентификаторов файла.
def read_csv_file_dtypes(path: Path, separator: str) -> dict[str, str]:
    columns = pd.read_csv(
        path,
        sep=separator,
        nrows=0,
        encoding="utf-8",
    ).columns
    return {name: dtype for name, dtype in IDENTIFIER_COLUMNS.items() if name in columns}


# Читает CSV с безопасными типами идентификаторов.
def read_csv_file(
    path: Path,
    separator: str = ",",
) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    dtypes = read_csv_file_dtypes(path, separator)
    return pd.read_csv(
        path,
        sep=separator,
        dtype=dtypes,
        encoding="utf-8",
        low_memory=False,
    )


# Читает Parquet-файл с проверкой существования.
def read_parquet_file(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    return pd.read_parquet(path)


# Сохраняет таблицу в Parquet без индекса.
def write_parquet_file(
    frame: pd.DataFrame,
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


# Сохраняет конкурсный CSV с разделителем точка с запятой.
def write_submission_csv(
    frame: pd.DataFrame,
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(
        path,
        sep=";",
        index=False,
        encoding="utf-8",
    )
