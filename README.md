# Transport Delay

Система прогнозирует задержку наземного транспорта на целевой остановке за 10–15 минут до планового прибытия.

Проект включает:

- offline-обучение CatBoost;
- локальную проверку по MAE;
- создание `submission.csv`;
- TCP Gateway для телеметрии;
- потоковую обработку через Redis Streams;
- независимый ML-service;
- Backend с WebSocket;
- диспетчерский дашборд.

## Требования

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker
- Docker Compose
- GNU Make — необязательно, все команды можно запускать вручную

## Структура датасета

Распакуйте датасет в `data/raw/`:

```text
data/raw/
├── train/
│   ├── traffic.csv
│   └── schedule.csv
├── test/
│   ├── traffic.csv
│   └── schedule.csv
├── validate/
│   ├── traffic.csv
│   ├── schedule_plan.csv
│   └── points.csv
├── labels/
│   ├── labels_train.csv
│   └── labels_test.csv
└── sample_submission.csv
```

Спецификацию NDTP положите в:

```text
docs/Emulator-and-Telematic-Packets-Specification.md
```

Docker-образ эмулятора:

```text
ndtp-telemetry-emulator.tar
```

## Установка зависимостей

Из корня проекта:

```bash
uv lock
uv sync --all-packages
```

Проверка проекта:

```bash
make test
make lint
```

Или одной командой:

```bash
make check
```

## Offline Data Science

### 1. Аудит данных

```bash
make audit
```

Отчёт появится в:

```text
data/interim/audit_report.json
```

### 2. Проверка baseline

```bash
make baseline
```

Будут рассчитаны:

- `prediction = 0`;
- `prediction = cur_dev_s`.

### 3. Построение признаков

```bash
make features-train
make features-test
```

Результаты:

```text
data/processed/train_features.parquet
data/processed/test_features.parquet
```

При построении признаков используется только телеметрия с:

```text
event_time <= T
```

### 4. Обучение модели

```bash
make train
```

Артефакт модели:

```text
ml/models/catboost_residual_v1/artifacts/model.cbm
```

Модель прогнозирует остаток:

```text
target_delay_s - cur_dev_s
```

Итоговый прогноз:

```text
prediction = cur_dev_s + predicted_residual
```

### 5. Локальная оценка

```bash
make evaluate
```

Модель должна показать MAE ниже baseline `cur_dev_s`.

### 6. Прогноз validate

```bash
make features-validate
make predict
```

Промежуточный файл:

```text
data/interim/validate_predictions.parquet
```

### 7. Создание submission.csv

```bash
make submission
```

Готовый файл:

```text
data/submissions/submission.csv
```

Формат:

```text
sample_id;prediction
131672_1767670500;120.0
122048_1767732000;45.0
```

## Подготовка online-контура

ML-service не запустится без обученного артефакта:

```text
ml/models/catboost_residual_v1/artifacts/model.cbm
```

Сначала выполните:

```bash
make features-train
make train
```

Скопируйте расписание для online-режима:

```bash
mkdir -p data/runtime
cp data/raw/validate/schedule_plan.csv \
  data/runtime/schedule_plan.csv
```

Создайте локальный файл окружения:

```bash
cp .env.example .env
```

## Запуск online-системы

```bash
make up
```

Просмотр журналов:

```bash
make logs
```

Остановка:

```bash
make down
```

Сервисы:

| Сервис | Адрес |
| --- | --- |
| Dashboard | http://localhost:8080 |
| Backend Swagger | http://localhost:8000/docs |
| Backend Health | http://localhost:8000/api/v1/health |
| ML Swagger | http://localhost:8001/docs |
| ML Health | http://localhost:8001/api/v1/health |
| Gateway TCP | localhost:19000 |
| Redis | localhost:6379 |

## Отправка тестовой телеметрии

По умолчанию Gateway использует режим:

```text
GATEWAY_DECODER=json_lines
```

Пример пакета:

```json
{
  "tr_id": "131672",
  "peerAddress": "131672",
  "packetId": "1",
  "timestamp": 1767670500,
  "longitude": 376173000,
  "latitude": 557558000,
  "speedAvg": 21.5,
  "course": 180,
  "location_valid": true
}
```

Linux/macOS:

```bash
printf '%s\n' \
'{"tr_id":"131672","peerAddress":"131672","packetId":"1","timestamp":1767670500,"longitude":376173000,"latitude":557558000,"speedAvg":21.5,"course":180,"location_valid":true}' \
| nc localhost 19000
```

Python-вариант:

```bash
python - <<'PY'
import json
import socket

packet = {
    "tr_id": "131672",
    "peerAddress": "131672",
    "packetId": "1",
    "timestamp": 1767670500,
    "longitude": 376173000,
    "latitude": 557558000,
    "speedAvg": 21.5,
    "course": 180,
    "location_valid": True,
}

with socket.create_connection(("localhost", 19000)) as connection:
    connection.sendall((json.dumps(packet) + "\n").encode("utf-8"))
PY
```

`tr_id` должен существовать в:

```text
data/runtime/schedule_plan.csv
```

В расписании должна быть остановка с плановым временем в окне:

```text
текущее время + 10 минут < time_begin <= текущее время + 15 минут
```

## Запуск NDTP-эмулятора

Загрузка образа:

```bash
docker load -i ndtp-telemetry-emulator.tar
```

Запуск:

```bash
docker run --rm \
  -p 18080:18080 \
  --add-host=host.docker.internal:host-gateway \
  --name ndtp-emu \
  ndtp-telemetry-emulator:1.0
```

Для настоящего бинарного потока установите:

```dotenv
GATEWAY_DECODER=ndtp
```

Текущий `ndtp.py` является защищённой заглушкой. Его нужно реализовать по точной бинарной раскладке из официальной спецификации:

```text
docs/Emulator-and-Telematic-Packets-Specification.md
```

Без реализации framing, byte order, offsets и checksum бинарный режим не запустится. JSON Lines можно использовать для разработки и демонстрации остального контура.

## Текущее отклонение cur_dev_s

В offline-данных `cur_dev_s` предоставляется организаторами.

В online-контуре значение хранится в Redis:

```text
current-deviation:<tr_id>
```

Если значение ещё не рассчитано или не передано внешней системой, Feature Worker использует fallback:

```text
cur_dev_s = 0
```

Для промышленного режима требуется вычисление фактического прохождения последней остановки по GPS/map matching или интеграция с диспетчерской системой.

## Поток данных

```text
TCP telemetry
→ Gateway
→ Redis Stream telemetry.v1
→ Feature Worker
→ ML-service
→ Redis Stream predictions.v1
→ Backend
→ WebSocket
→ Dashboard
```

## Замена модели

Активная модель задаётся в:

```text
ml/configs/active_model.yaml
```

Пример:

```yaml
plugin: catboost_residual_v1
version: 1.0.0
```

После изменения конфигурации:

```bash
curl -X POST \
  http://localhost:8001/api/v1/reload \
  -H "Content-Type: application/json" \
  -d '{}'
```

Подробнее:

```text
docs/model-plugin.md
```

## Документация

- `docs/architecture.md` — архитектура и потоки данных;
- `docs/model-plugin.md` — создание и подключение моделей;
- `docs/Emulator-and-Telematic-Packets-Specification.md` — спецификация NDTP.

## Очистка

Удаление сгенерированных offline-файлов:

```bash
make clean-generated
```

Удаление контейнеров:

```bash
docker compose down
```

Удаление контейнеров вместе с Redis volume:

```bash
docker compose down -v
```

Последняя команда безвозвратно удаляет оперативные данные Redis.