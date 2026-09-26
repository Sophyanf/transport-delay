import pytest
from transport_ml.metrics import mean_absolute_error


# Проверяет вычисление средней абсолютной ошибки.
def test_mean_absolute_error() -> None:
    target = [10.0, 20.0, 30.0]
    prediction = [12.0, 18.0, 34.0]
    assert mean_absolute_error(target, prediction) == pytest.approx(8 / 3)


# Проверяет запрет массивов разной длины.
def test_mean_absolute_error_rejects_different_shapes() -> None:
    with pytest.raises(ValueError):
        mean_absolute_error([1.0, 2.0], [1.0])
