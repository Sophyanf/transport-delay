# Модельные плагины

## Назначение

Модель подключается к системе как заменяемый плагин.

Для добавления модели не требуется изменять:

- Gateway;
- Feature Worker;
- Backend;
- Dashboard;
- ML-service.

Изменяются только:

```text
ml/models/<plugin>/
ml/configs/active_model.yaml
```

## Структура плагина

```text
ml/models/new_model_v1/
├── model.yaml
├── model.py
├── requirements.txt
└── artifacts/
    ├── .gitkeep
    └── model.bin
```

## Манифест model.yaml

Пример:

```yaml
name: new_model
version: 1.0.0
entrypoint: model.py::NewDelayModel
target_type: direct
feature_set: feature_set_v1
artifact: artifacts/model.bin
metadata:
  description: Example delay model
  clip_lower_s: -900
  clip_upper_s: 1800
```

Поля:

| Поле | Описание |
| --- | --- |
| `name` | Логическое имя модели |
| `version` | Версия модели |
| `entrypoint` | Файл и класс реализации |
| `target_type` | `direct`, `residual` или `ensemble` |
| `feature_set` | Требуемый набор признаков |
| `artifact` | Относительный путь к артефакту |
| `metadata` | Дополнительные параметры |

В `artifact` запрещены:

- абсолютные пути;
- переходы через `..`.

## Контракт DelayModel

Модель должна реализовать:

```python
class DelayModel(Protocol):
    name: str
    version: str
    feature_names: tuple[str, ...]

    def fit(self, features, target) -> None: ...

    def predict(self, features) -> np.ndarray: ...

    def load(self) -> None: ...

    def save(self) -> None: ...
```

Требования:

- `fit` обучает модель;
- `predict` возвращает задержку в секундах;
- `load` загружает артефакт;
- `save` сохраняет артефакт;
- длина результата `predict` равна числу строк;
- прогнозы должны быть конечными числами.

## Пример реализации

```python
from pathlib import Path

import numpy as np
import pandas as pd

from transport_model_core import ModelManifest


class NewDelayModel:
    def __init__(
        self,
        manifest: ModelManifest,
        plugin_directory: Path,
    ) -> None:
        self.name = manifest.name
        self.version = manifest.version
        self.feature_names = ("cur_dev_s",)
        self._artifact_path = plugin_directory / manifest.artifact
        self._offset = 0.0

    # Обучает постоянную поправку к текущей задержке.
    def fit(
        self,
        features: pd.DataFrame,
        target: pd.Series,
    ) -> None:
        residual = target - features["cur_dev_s"]
        self._offset = float(residual.median())

    # Возвращает итоговую задержку в секундах.
    def predict(self, features: pd.DataFrame) -> np.ndarray:
        baseline = features["cur_dev_s"].to_numpy(dtype=float)
        return baseline + self._offset

    # Загружает поправку из артефакта.
    def load(self) -> None:
        self._offset = float(self._artifact_path.read_text(encoding="utf-8"))

    # Сохраняет поправку в артефакт.
    def save(self) -> None:
        self._artifact_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        self._artifact_path.write_text(
            str(self._offset),
            encoding="utf-8",
        )
```

## Residual-модель

Residual-модель обучается на:

```text
target_delay_s - cur_dev_s
```

Но метод `predict` должен вернуть итоговый результат:

```text
cur_dev_s + predicted_residual
```

ML-service не выполняет residual-постобработку.

## Direct-модель

Direct-модель сразу прогнозирует:

```text
target_delay_s
```

## Ensemble-модель

Ансамбль также оформляется отдельным плагином.

Пример:

```text
ml/models/ensemble_v1/
├── model.yaml
├── model.py
├── requirements.txt
└── artifacts/
```

Именно плагин ансамбля отвечает за:

- загрузку дочерних моделей;
- веса;
- clipping;
- итоговую комбинацию прогнозов.

## Активная модель

Файл:

```text
ml/configs/active_model.yaml
```

Пример:

```yaml
plugin: catboost_residual_v1
version: 1.0.0
```

Папка плагина:

```text
ml/models/catboost_residual_v1/
```

Версия в `active_model.yaml` должна совпадать с `model.yaml`.

## Обучение новой модели

```bash
uv run --package transport-ml \
  python ml/scripts/train.py \
  --plugin new_model_v1 \
  --version 1.0.0 \
  --features data/processed/train_features.parquet \
  --labels data/raw/labels/labels_train.csv
```

Артефакт сохраняется в папку, указанную в `model.yaml`.

## Переключение модели

Измените:

```text
ml/configs/active_model.yaml
```

Затем вызовите:

```bash
curl -X POST \
  http://localhost:8001/api/v1/reload \
  -H "Content-Type: application/json" \
  -d '{}'
```

Явное переключение без изменения конфигурации:

```bash
curl -X POST \
  http://localhost:8001/api/v1/reload \
  -H "Content-Type: application/json" \
  -d '{
    "plugin": "new_model_v1",
    "version": "1.0.0"
  }'
```

Проверка:

```bash
curl http://localhost:8001/api/v1/model
```

## Пути моделей

`model_core` не содержит жёсткой зависимости от `ml/models`.

Путь передаётся переменной:

```text
MODEL_ROOT=/workspace/ml/models
```

Путь к активной конфигурации:

```text
ACTIVE_MODEL_CONFIG=/workspace/ml/configs/active_model.yaml
```

При локальном запуске:

```bash
export MODEL_ROOT="$(pwd)/ml/models"
export ACTIVE_MODEL_CONFIG="$(pwd)/ml/configs/active_model.yaml"
```

## Docker mount

Docker Compose подключает каталоги:

```yaml
volumes:
  - type: bind
    source: ./ml/models
    target: /workspace/ml/models
    read_only: true
  - type: bind
    source: ./ml/configs
    target: /workspace/ml/configs
    read_only: true
```

Обучение выполняется на хосте и записывает артефакт в:

```text
./ml/models/<plugin>/artifacts/
```

ML-service видит этот файл как:

```text
/workspace/ml/models/<plugin>/artifacts/
```

## Зависимости модели

`requirements.txt` документирует зависимости плагина, но не устанавливается автоматически при `/reload`.

Все зависимости активной модели должны присутствовать в контейнере ML-service.

Для текущей модели используются:

```text
CatBoost
NumPy
Pandas
```

Для PyTorch, ONNX Runtime или TensorRT рекомендуется отдельный inference image.

## Безопасная замена артефакта

Правильный порядок:

1. Обучить новую версию.
2. Сохранить её во временный файл.
3. Проверить загрузку.
4. Атомарно заменить основной артефакт.
5. Вызвать `/reload`.

`ModelManager` загружает новую модель до получения блокировки на замену. Если загрузка завершилась ошибкой, предыдущая активная модель сохраняется.

## Хранение артефактов

Артефакты исключены из Git:

```gitignore
ml/models/*/artifacts/*
!ml/models/*/artifacts/.gitkeep
```

В дальнейшем можно использовать:

- DVC;
- S3;
- MinIO;
- MLflow Model Registry;
- отдельный Docker volume.