# Хакатон Московского транспорта · Предиктор задержек

## О проекте

**Transport Delay** — система прогнозирования задержек наземного транспорта. По потоковой
телеметрии (GPS-координаты, скорость, курс) модель за 10–15 минут до планового прибытия
предсказывает отклонение автобуса от графика на целевой остановке — в секундах.

Диспетчер видит прогнозы в реальном времени на дашборде: карта с положением ТС, список
инцидентов (опозданий и опережений) и WebSocket-обновления без перезагрузки страницы.

Проект решает задачу в двух контурах:

- **offline** — обучение и оценка модели CatBoost на исторических данных, генерация
  `submission.csv` для автоматической проверки;
- **online** — полный real-time контур: приём живой телеметрии, потоковая обработка
  и онлайн-инференс той же модели.

## Архитектура

Поток данных:

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

| Компонент | Роль |
| --- | --- |
| Gateway | принимает телеметрию по TCP, декодирует пакеты, пишет в Redis Stream |
| Feature Worker | собирает признаки по расписанию и телеметрии, формирует запросы к ML |
| ML-service | рассчитывает прогноз задержки по активной модели, пишет в `predictions.v1` |
| Backend | читает прогнозы, ведёт инциденты и состояния ТС, раздаёт API и WebSocket |
| Dashboard | диспетчерский интерфейс: карта, списки, вкладка проверки submission |

## Задача (постановка от организаторов)

Прогнозная точка — пара `(tr_id, T)`: момент `T`, на который известна вся телеметрия ТС.
Нужно предсказать **фактическую задержку** (в секундах) на первой остановке этого ТС,
чьё плановое время прибытия попадает в окно `(T+10 мин, T+15 мин]`.

- **Задержка = факт − план.** Положительная — опоздание, отрицательная — опережение.
- Целевая остановка и её плановое время даны (`target_stop_id`, `target_time_begin`).
- **Правило честности (анти-утечка):** при прогнозе для точки `T` используются только данные,
  доступные на момент `T` — телеметрия с `event_time ≤ T` и подсказка `cur_dev_s`.

Метрика — **MAE** (средняя абсолютная ошибка прогноза задержки, секунды):

```text
MAE      = mean(|факт − прогноз|)
mae_zero = mean(|факт|)
score    = max(0, min(1, (mae_zero − MAE) / (mae_zero − MAE_TARGET)))
```

Baseline `sample_submission.csv` (прогноз = `cur_dev_s`) даёт ≈ 0.40 — этот «пол» нужно
превзойти обученной моделью. Нулевой прогноз даёт `score = 0`.

По `validate/` фактических задержек нет и не будет: проверка идёт по скрытому эталону
на стороне платформы. Загружается `submission.csv` с прогнозами.

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

Отчёт появится в `data/interim/audit_report.json`.

### 2. Проверка baseline

```bash
make baseline
```

Рассчитываются два эталона: `prediction = 0` и `prediction = cur_dev_s`.

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

При построении признаков используется только телеметрия с `event_time <= T` — утечек будущего нет.

### 4. Обучение модели

```bash
make train
```

Артефакт модели: `ml/models/catboost_residual_v1/artifacts/model.cbm`.

Модель прогнозирует остаток `target_delay_s - cur_dev_s`, итоговый прогноз:

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

Промежуточный файл: `data/interim/validate_predictions.parquet`.

### 7. Создание submission.csv

```bash
make submission
```

Готовый файл: `data/submissions/submission.csv`. Формат — разделитель `;`, UTF-8,
заголовок обязателен, ровно две колонки, полный покрытие всех `sample_id` без дублей:

```text
sample_id;prediction
131672_1767670500;120.0
122048_1767732000;45.0
130072_1767732000;-30.0
```

## Подготовка online-контура

ML-service не запустится без обученного артефакта
`ml/models/catboost_residual_v1/artifacts/model.cbm`. Сначала выполните:

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

По умолчанию Gateway использует режим `GATEWAY_DECODER=json_lines`. Пример пакета:

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

`tr_id` должен существовать в `data/runtime/schedule_plan.csv`. В расписании должна быть
остановка с плановым временем в окне: текущее время + 10 минут < `time_begin` ≤ текущее время + 15 минут.

## Запуск NDTP-эмулятора

CSV-файлы — это уже раскодированная телеметрия: строка `traffic.csv` соответствует
навигационной ячейке `G6CellNav00` протокола NDTP. Для обучения модели эмулятор не нужен —
он требуется для real-time контура: живой NDTP-поток, приём, парсинг пакетов и онлайн-инференс.

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

Затем `POST /api/config` (порт 18080) настраивает устройства и период отправки;
эмулятор по TCP шлёт NDTP-пакеты на ваш `targetHost:targetPort`.

Соответствие полей `traffic.csv` ↔ `G6CellNav00`:

| Колонка CSV | Поле NDTP | Преобразование |
|---|---|---|
| `event_time` / `gps_time` | `timestamp` | Unix-секунды → datetime |
| `lon` | `longitude` | `longitude / 1e7`, знак из `extraDopBit6` (E/W) |
| `lat` | `latitude` | `latitude / 1e7`, знак из `extraDopBit5` (N/S) |
| `alt` | `altitude` | метры |
| `speed` | `speedAvg` | км/ч |
| `heading` | `course` | градусы |
| `location_valid` | `extraDopBit7` | флаг достоверности координат |
| `unit_id` | `peerAddress` (`unitId`) | ID бортового терминала |

Для настоящего бинарного потока установите в окружении Gateway:

```dotenv
GATEWAY_DECODER=ndtp
```

Текущий `ndtp.py` является защищённой заглушкой: реализуйте его по точной бинарной раскладке
из `docs/Emulator-and-Telematic-Packets-Specification.md` (framing, byte order, offsets, checksum).
Без этого бинарный режим не запустится — для разработки и демонстрации используйте JSON Lines.

## Текущее отклонение cur_dev_s

В offline-данных `cur_dev_s` предоставляется организаторами. В online-контуре значение
хранится в Redis по ключу `current-deviation:<tr_id>`. Если значение ещё не рассчитано
или не передано внешней системой, Feature Worker использует fallback `cur_dev_s = 0`.

Для промышленного режима требуется вычисление фактического прохождения последней остановки
по GPS/map matching или интеграция с диспетчерской системой.

## Замена модели

Активная модель задаётся в `ml/configs/active_model.yaml`:

```yaml
plugin: catboost_residual_v1
version: 1.0.0
```

После изменения конфигурации перезагрузите модель:

```bash
curl -X POST \
  http://localhost:8001/api/v1/reload \
  -H "Content-Type: application/json" \
  -d '{}'
```

Подробнее — в `docs/model-plugin.md`.

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
