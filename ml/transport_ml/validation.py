import numpy as np
import pandas as pd


# Проверяет уникальность указанного идентификатора.
def validate_unique_identifier(
    frame: pd.DataFrame,
    column: str,
    frame_name: str,
) -> None:
    if column not in frame:
        raise ValueError(f"{frame_name} misses column: {column}")
    duplicates = int(frame[column].duplicated().sum())
    if duplicates:
        raise ValueError(f"{frame_name} contains {duplicates} duplicate {column}")


# Проверяет покрытие всех строк разметки признаками.
def validate_feature_coverage(
    features: pd.DataFrame,
    labels: pd.DataFrame,
) -> None:
    validate_unique_identifier(features, "sample_id", "features")
    validate_unique_identifier(labels, "sample_id", "labels")
    feature_ids = set(features["sample_id"].astype(str))
    label_ids = set(labels["sample_id"].astype(str))
    missing = label_ids.difference(feature_ids)
    extra = feature_ids.difference(label_ids)
    if missing:
        raise ValueError(f"Features miss {len(missing)} label samples")
    if extra:
        raise ValueError(f"Features contain {len(extra)} unknown samples")


# Проверяет строгий формат конкурсного файла.
def validate_submission(
    submission: pd.DataFrame,
    template: pd.DataFrame,
) -> None:
    validate_submission_columns(submission)
    validate_unique_identifier(submission, "sample_id", "submission")
    validate_unique_identifier(template, "sample_id", "template")
    validate_submission_coverage(submission, template)
    validate_submission_predictions(submission)


# Проверяет названия и порядок колонок submission.
def validate_submission_columns(submission: pd.DataFrame) -> None:
    expected = ["sample_id", "prediction"]
    if list(submission.columns) != expected:
        raise ValueError(f"Submission columns must be: {expected}")


# Проверяет покрытие и порядок sample_id.
def validate_submission_coverage(
    submission: pd.DataFrame,
    template: pd.DataFrame,
) -> None:
    actual = submission["sample_id"].astype(str).tolist()
    expected = template["sample_id"].astype(str).tolist()
    if actual != expected:
        raise ValueError("Submission sample_id order differs from template")


# Проверяет числовые значения прогнозов.
def validate_submission_predictions(
    submission: pd.DataFrame,
) -> None:
    prediction = pd.to_numeric(
        submission["prediction"],
        errors="coerce",
    )
    if prediction.isna().any():
        raise ValueError("Submission contains missing predictions")
    if not np.isfinite(prediction.to_numpy(dtype=float)).all():
        raise ValueError("Submission contains non-finite predictions")
