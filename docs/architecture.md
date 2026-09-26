docs/architecture.md

markdown
# Архитектура Transport Delay

## Цель

Система прогнозирует задержку транспортного средства на целевой остановке за 10–15 минут до планового прибытия.

Решение разделено на два контура:

1. Offline Data Science.
2. Online MVP.

## Offline-контур

```text
train/test CSV
      |
      v
Feature Pipeline
      |
      v
Parquet features
      |
      v
CatBoost training
      |
      v
model.cbm
      |
      v
validate prediction
      |
      v
submission.csv
```

### Исходные данные

```text
data/raw/train/
data/raw/test/
data/raw/validate/
data/raw/labels/
```

### Feature Pipeline

Общий пакет:

```text
packages/feature_pipeline/
```

Он используется:

- offline-скриптами;
- online Feature Worker.

Это предотвращает расхождение признаков между обучением и инференсом.

Основное правило:

```text
event_time <= T
```

Телеметрия после момента прогнозирования не используется.

### Модель

Первая модель:

```text
ml/models/catboost_residual_v1/
```

Она прогнозирует:

```text
residual = target_delay_s - cur_dev_s
```

И возвращает:

```text
prediction = cur_dev_s + residual
```

Основная метрика:

```text
MAE = mean(abs(target_delay_s - prediction))
```

## Online-контур

```text
Эмулятор / транспортное средство
                 |
                 | TCP
                 v
              Gateway
                 |
                 | Redis Stream telemetry.v1
                 v
          Feature Worker
                 |
                 | HTTP POST /predict
                 v
            ML-service
                 |
                 | Redis Stream predictions.v1
                 v
              Backend
                 |
                 | HTTP + WebSocket
                 v
             Dashboard
```

## Gateway

Каталог:

```text
apps/gateway/
```

Ответственность:

- приём TCP-соединений;
- выделение пакетов из TCP-потока;
- декодирование входного формата;
- валидация `TelemetryEvent`;
- публикация в Redis Streams;
- публикация ошибочных сообщений в dead-letter stream.

Основной поток:

```text
telemetry.v1
```

Dead-letter поток:

```text
telemetry.dead-letter.v1
```

Доступные декодеры:

- `json_lines` — рабочий режим разработки;
- `ndtp` — требует реализации по официальной бинарной спецификации.

Gateway не рассчитывает признаки и не вызывает модель.

## Redis

Redis используется как:

- брокер событий;
- краткосрочное хранилище телеметрии;
- хранилище текущего отклонения;
- оперативное хранилище инцидентов.

Основные структуры:

```text
telemetry.v1
telemetry.dead-letter.v1
predictions.v1
vehicle-state:<tr_id>
current-deviation:<tr_id>
prediction-point:<sample_id>
incident:<incident_id>
incident:index
```

Redis запускается через Docker Compose.

Данные сохраняются в Docker volume:

```text
redis-data
```

Redis не является долговременным аналитическим хранилищем.

## Feature Worker

Каталог:

```text
apps/feature_worker/
```

Ответственность:

1. Читать `TelemetryStreamEvent`.
2. Хранить последние 20 минут телеметрии.
3. Находить целевую остановку.
4. Создавать прогнозную точку.
5. Рассчитывать признаки.
6. Вызывать ML-service.
7. Публиковать результат в `predictions.v1`.

### Выбор остановки

Для текущего времени `T` выбирается первая остановка, удовлетворяющая условию:

```text
T + 10 минут < time_begin <= T + 15 минут
```

### Online-состояние

История каждого ТС хранится в Redis Sorted Set:

```text
vehicle-state:<tr_id>
```

Score:

```text
event_time Unix timestamp
```

Период хранения:

```text
VEHICLE_STATE_RETENTION_S=1200
```

### Защита от повторных прогнозов

Используется ключ:

```text
prediction-point:<sample_id>
```

Ключ создаётся с `NX` и TTL, поэтому несколько экземпляров планировщика не должны создавать одинаковый прогноз одновременно.

### cur_dev_s

Offline-значение предоставлено датасетом.

Online-значение читается из:

```text
current-deviation:<tr_id>
```

При отсутствии используется fallback `0`. Полноценная реализация должна обновлять значение по фактическому прохождению остановок.

## ML-service

Каталог:

```text
apps/ml_service/
```

Endpoints:

```text
POST /api/v1/predict
POST /api/v1/predict-batch
POST /api/v1/reload
GET  /api/v1/model
GET  /api/v1/health
```

ML-service:

- не знает конкретный тип активной модели;
- использует `ModelManager`;
- получает готовые признаки;
- возвращает задержку в секундах;
- рассчитывает риск, confidence и reason code;
- поддерживает горячую замену модели.

Активная модель:

```text
ml/configs/active_model.yaml
```

Каталог моделей:

```text
ml/models/
```

## Model Core

Каталог:

```text
packages/model_core/
```

Содержит:

- `DelayModel`;
- `ModelManifest`;
- `ModelLoader`;
- `ModelManager`.

Зависимость направлена так:

```text
ML-service
    |
    v
ModelManager
    |
    v
ModelLoader
    |
    v
ml/models/<plugin>
```

`model_core` не зависит от конкретного CatBoost или PyTorch-класса.

## Backend

Каталог:

```text
apps/backend/
```

Ответственность:

- читать `PredictionResultStreamEvent`;
- преобразовывать прогноз в инцидент;
- сохранять инцидент в Redis;
- предоставлять REST API;
- рассылать обновления по WebSocket;
- обрабатывать действия диспетчера.

REST API:

```text
GET  /api/v1/incidents
GET  /api/v1/incidents/{incident_id}
POST /api/v1/incidents/{incident_id}/ack
POST /api/v1/incidents/{incident_id}/close
GET  /api/v1/statistics
GET  /api/v1/health
WS   /api/v1/stream
```

### Состояния инцидентов

```text
normal
warning
critical
closed
```

### Уровни риска

```text
green
yellow
red
```

## Dashboard

Каталог:

```text
apps/dashboard/
```

Dashboard показывает:

- число инцидентов;
- число красных и жёлтых рисков;
- среднюю прогнозируемую задержку;
- ТС;
- целевую остановку;
- причину;
- рекомендацию;
- действия подтверждения и закрытия.

Nginx:

- раздаёт статические файлы;
- проксирует `/api/` в Backend;
- поддерживает WebSocket upgrade.

## Контракты

Каталог:

```text
packages/contracts/
```

Основные контракты:

```text
TelemetryEvent
TelemetryStreamEvent
PredictionRequest
PredictionResponse
PredictionResultStreamEvent
HealthResponse
ModelInfo
ReloadRequest
```

Сервисы не импортируют код друг друга.

Допустимое взаимодействие:

- Redis Streams;
- HTTP;
- WebSocket;
- общие контракты.

## Docker-сервисы

```text
redis
gateway
feature-worker
ml-service
backend
dashboard
```

Все сервисы находятся в сети:

```text
transport-network
```

Открытые порты:

| Компонент | Порт |
| --- | --- |
| Redis | 6379 |
| Gateway | 19000 |
| ML-service | 8001 |
| Backend | 8000 |
| Dashboard | 8080 |

## Отказоустойчивость

### Gateway

- ошибочный пакет отправляется в dead-letter stream;
- ошибка одного пакета не должна закрывать соединение;
- TCP-буфер ограничен по размеру.

### Feature Worker

- телеметрия подтверждается после сохранения;
- при ошибке ML прогнозная точка освобождается;
- следующая итерация может повторить запрос;
- duplicate prediction предотвращается Redis-ключом.

### ML-service

- новая модель загружается до замены старой;
- при ошибке reload старая модель остаётся активной;
- healthcheck возвращает `not_ready`, если модель не загружена.

### Backend

- сообщение подтверждается после сохранения инцидента;
- инциденты имеют TTL;
- WebSocket-ошибка одного клиента не прерывает рассылку другим.

## Ограничения первой версии

Не реализованы полностью:

- бинарный NDTP-декодер;
- map matching;
- вычисление online `cur_dev_s` по остановкам;
- PostgreSQL/PostGIS;
- долговременная история;
- маршрутная карта;
- GRU/Transformer;
- what-if моделирование.

Эти ограничения не мешают offline-созданию `submission.csv` и демонстрации online-потока в JSON