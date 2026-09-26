import numpy as np


# Преобразует значения метрики в одномерный массив.
def mean_absolute_error_array(values: object) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise ValueError("Metric input must be one-dimensional")
    if not np.isfinite(array).all():
        raise ValueError("Metric input contains non-finite values")
    return array


# Вычисляет среднюю абсолютную ошибку.
def mean_absolute_error(
    target: object,
    prediction: object,
) -> float:
    target_array = mean_absolute_error_array(target)
    prediction_array = mean_absolute_error_array(prediction)
    if target_array.shape != prediction_array.shape:
        raise ValueError("Target and prediction shapes differ")
    return float(np.mean(np.abs(target_array - prediction_array)))


# Вычисляет улучшение MAE относительно baseline.
def mean_absolute_error_improvement(
    target: object,
    prediction: object,
    baseline: object,
) -> float:
    model_mae = mean_absolute_error(target, prediction)
    baseline_mae = mean_absolute_error(target, baseline)
    return float(baseline_mae - model_mae)
