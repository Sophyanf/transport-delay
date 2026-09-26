from typing import Protocol, runtime_checkable

import numpy as np
import pandas as pd


@runtime_checkable
class DelayModel(Protocol):
    name: str
    version: str
    feature_names: tuple[str, ...]

    # Обучает модель на признаках и целевой задержке.
    def fit(
        self,
        features: pd.DataFrame,
        target: pd.Series,
    ) -> None: ...

    # Возвращает итоговую задержку в секундах.
    def predict(self, features: pd.DataFrame) -> np.ndarray: ...

    # Загружает обученный артефакт модели.
    def load(self) -> None: ...

    # Сохраняет обученный артефакт модели.
    def save(self) -> None: ...
