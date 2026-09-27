import io
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import HTTPException
from fastapi.responses import StreamingResponse


class SubmissionService:
    # Создаёт сервис выгрузки submission.csv.
    def __init__(
        self,
        points_path: Path,
        predictions_path: Path,
        submission_path: Path,
    ) -> None:
        self._points_path = points_path
        self._predictions_path = predictions_path
        self._submission_path = submission_path

    # Возвращает проверенный submission.csv.
    def download(self) -> StreamingResponse:
        frame = self._load_submission()
        self._validate(frame)
        buffer = io.StringIO()
        frame.to_csv(buffer, sep=";", index=False)
        headers = {"Content-Disposition": 'attachment; filename="submission.csv"'}
        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="text/csv; charset=utf-8",
            headers=headers,
        )

    # Загружает готовый CSV или собирает его из Parquet.
    def _load_submission(self) -> pd.DataFrame:
        if self._submission_path.is_file():
            return pd.read_csv(
                self._submission_path,
                sep=";",
                dtype={"sample_id": str},
            )
        if not self._predictions_path.is_file():
            raise HTTPException(503, "Прогнозы validate ещё не сформированы")
        predictions = pd.read_parquet(self._predictions_path)
        return predictions[["sample_id", "prediction"]].copy()

    # Проверяет формат и покрытие validate.
    def _validate(self, frame: pd.DataFrame) -> None:
        if list(frame.columns) != ["sample_id", "prediction"]:
            raise HTTPException(500, "Некорректный формат submission")
        if not self._points_path.is_file():
            raise HTTPException(503, "validate/points.csv не найден")
        points = pd.read_csv(
            self._points_path,
            dtype={"sample_id": str},
        )
        actual = frame["sample_id"].astype(str).tolist()
        expected = points["sample_id"].astype(str).tolist()
        if set(actual) != set(expected) or len(actual) != len(expected):
            raise HTTPException(500, "Submission не покрывает все validate-точки")
        values = pd.to_numeric(frame["prediction"], errors="coerce")
        if values.isna().any() or not np.isfinite(values).all():
            raise HTTPException(500, "Submission содержит некорректные прогнозы")
