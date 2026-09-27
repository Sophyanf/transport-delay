import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastapi import HTTPException, UploadFile
from redis.asyncio import Redis


class ScoreService:
    # Создаёт сервис проверки конкурсных CSV.
    def __init__(
        self,
        redis: Redis,
        points_path: Path,
        ground_truth_path: Path,
        history_key: str,
        history_limit: int,
        mae_target: float,
    ) -> None:
        self._redis = redis
        self._points_path = points_path
        self._ground_truth_path = ground_truth_path
        self._history_key = history_key
        self._history_limit = history_limit
        self._mae_target = mae_target

    # Проверяет загруженный файл и рассчитывает score.
    async def upload(self, file: UploadFile) -> dict[str, Any]:
        content = await file.read()
        submission = self._read_submission(content)
        expected = self._read_expected()
        self._validate_submission(submission, expected)
        result = self._calculate_score(submission)
        result["filename"] = file.filename
        result["uploaded_at"] = datetime.now(UTC).isoformat()
        await self._save_history(result)
        return result

    # Возвращает историю загрузок.
    async def history(self) -> list[dict[str, Any]]:
        values = await self._redis.lrange(
            self._history_key,
            0,
            self._history_limit - 1,
        )
        return [json.loads(self._text(value)) for value in values]

    # Читает CSV с обязательным разделителем.
    def _read_submission(self, content: bytes) -> pd.DataFrame:
        try:
            text = content.decode("utf-8-sig")
            frame = pd.read_csv(
                io.StringIO(text),
                sep=";",
                dtype={"sample_id": str},
            )
        except (UnicodeDecodeError, pd.errors.ParserError) as error:
            raise HTTPException(400, "CSV должен быть UTF-8 и иметь разделитель ';'") from error
        if list(frame.columns) != ["sample_id", "prediction"]:
            raise HTTPException(400, "Ожидаются колонки sample_id;prediction")
        return frame

    # Читает ожидаемые sample_id.
    def _read_expected(self) -> pd.DataFrame:
        if not self._points_path.is_file():
            raise HTTPException(503, "Файл прогнозных точек не найден")
        return pd.read_csv(
            self._points_path,
            dtype={"sample_id": str},
            low_memory=False,
        )

    # Проверяет покрытие, дубли и тип прогноза.
    def _validate_submission(
        self,
        submission: pd.DataFrame,
        expected: pd.DataFrame,
    ) -> None:
        if submission["sample_id"].duplicated().any():
            raise HTTPException(400, "CSV содержит дубли sample_id")
        prediction = pd.to_numeric(submission["prediction"], errors="coerce")
        if prediction.isna().any() or not np.isfinite(prediction).all():
            raise HTTPException(400, "prediction должен содержать только числа")
        actual_ids = set(submission["sample_id"])
        expected_ids = set(expected["sample_id"].astype(str))
        missing = expected_ids - actual_ids
        extra = actual_ids - expected_ids
        if missing or extra:
            detail = f"Неполное покрытие: пропущено {len(missing)}, лишних {len(extra)}"
            raise HTTPException(400, detail)

    # Рассчитывает proxy MAE и score при наличии разметки.
    def _calculate_score(
        self,
        submission: pd.DataFrame,
    ) -> dict[str, Any]:
        base = {
            "valid": True,
            "rows": len(submission),
            "mae": None,
            "mae_zero": None,
            "score": None,
            "mode": "validation_only",
        }
        if not self._ground_truth_path.is_file():
            return base
        truth = pd.read_csv(
            self._ground_truth_path,
            dtype={"sample_id": str},
            low_memory=False,
        )
        if "target_delay_s" not in truth:
            return base
        merged = truth.merge(submission, on="sample_id", how="inner")
        if len(merged) != len(submission):
            return base
        return self._calculate_score_metrics(merged, base)

    # Вычисляет численные метрики загрузки.
    def _calculate_score_metrics(
        self,
        merged: pd.DataFrame,
        base: dict[str, Any],
    ) -> dict[str, Any]:
        target = merged["target_delay_s"].to_numpy(dtype=float)
        prediction = merged["prediction"].to_numpy(dtype=float)
        mae = float(np.mean(np.abs(target - prediction)))
        mae_zero = float(np.mean(np.abs(target)))
        denominator = mae_zero - self._mae_target
        raw_score = 0.0 if denominator <= 0 else (mae_zero - mae) / denominator
        return {
            **base,
            "mae": mae,
            "mae_zero": mae_zero,
            "score": float(np.clip(raw_score, 0.0, 1.0)),
            "mode": "proxy_test_labels",
        }

    # Сохраняет результат загрузки в Redis.
    async def _save_history(self, result: dict[str, Any]) -> None:
        async with self._redis.pipeline(transaction=True) as pipeline:
            pipeline.lpush(
                self._history_key,
                json.dumps(result, ensure_ascii=False),
            )
            pipeline.ltrim(self._history_key, 0, self._history_limit - 1)
            await pipeline.execute()

    # Преобразует Redis-значение в строку.
    def _text(self, value: object) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)
