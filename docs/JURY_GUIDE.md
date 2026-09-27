# Инструкция для жюри · Transport Delay

Краткий сценарий демонстрации: запуск системы за 5 минут, подача потока телеметрии,
просмотр прогнозов и алертов в реальном времени, проверка метрик модели.

**Что вы увидите в итоге:** на дашборде — карту с движением транспорта, список инцидентов
(опозданий/опережений) и прогнозы задержек, обновляющиеся без перезагрузки страницы.

---

## 1. Подготовка (один раз)

### Требования

- Python 3.12+ и [uv](https://docs.astral.sh/uv/)
- Docker и Docker Compose
- Датасет хакатона, распакованный в `data/raw/` (см. README, раздел «Структура датасета»)

### Установка зависимостей

Из корня проекта:

```bash
uv lock
uv sync --all-packages
```

### Обучение модели (если артефакта ещё нет)

Проверьте наличие артефакта:

```bash
ls ml/models/catboost_residual_v1/artifacts/model.cbm
```

Если файл отсутствует, обучите модель:

```bash
make features-train
make train
```

### Подготовка online-контура

```bash
mkdir -p data/runtime
cp data/raw/validate/schedule_plan.csv data/runtime/schedule_plan.csv
cp .env.example .env
```

## 2. Запуск системы

```bash
make up
```

Дождитесь статуса всех сервисов (`make logs` — посмотреть журнал, Ctrl+C — выйти из просмотра).

Проверка здоровья:

```bash
curl http://localhost:8000/api/v1/health
curl http://localhost:8001/api/v1/health
```

Оба должны ответить JSON со статусом `ok`.

| Сервис | Адрес |
| --- | --- |
| Дашборд | http://localhost:8080 |
| Backend Swagger | http://localhost:8000/docs |
| ML Swagger | http://localhost:8001/docs |
| Gateway TCP | localhost:19000 |
| Redis | localhost:6379 |

## 3. Открыть дашборд

Откройте в браузере: **http://localhost:8080**

На дашборде доступны:

- **карта** с текущим положением транспортных средств;
- **список ТС** с активными прогнозами задержек;
- **инциденты** — опоздания (задержка > +120 с) и опережения (< −60 с), с уровнем риска
  (green/yellow/red);
- обновления приходят по WebSocket в реальном времени, перезагрузка не требуется.

## 4. Подать поток телеметрии

Выберите один из двух способов.

### Способ А: ручная отправка пакета (быстрая проверка)

Gateway работает в режиме `GATEWAY_DECODER=json_lines` по умолчанию. Отправьте пакет:

```bash
printf '%s\n' \
'{"tr_id":"131672","peerAddress":"131672","packetId":"1","timestamp":1767670500,"longitude":376173000,"latitude":557558000,"speedAvg":21.5,"course":180,"location_valid":true}' \
| nc localhost 19000
```

Условия, при которых по пакету возникнет прогноз:

- `tr_id` существует в `data/runtime/schedule_plan.csv`;
- в расписании этого ТС есть остановка с плановым временем в окне
  `текущее время + 10 минут < time_begin ≤ текущее время + 15 минут`.

Через 2–5 секунд после отправки:

- в списке ТС на дашборде появится/обновится машина `131672`;
- при приближении к окну прогноза появится запись с прогнозом задержки в секундах;
- при выходе за пороги (±120/−60 с) возникнет инцидент.

> `timestamp` в пакете — Unix-время в секундах. Если время пакета сильно отстаёт от
> текущего, контур посчитает телеметрию устаревшей (`reason_code: STALE_TELEMETRY`).
> Для актуального пакета подставьте текущее время: `date +%s`.

### Способ Б: NDTP-эмулятор (полный real-time контур)

Загрузка и запуск эмулятора:

```bash
docker load -i ndtp-telemetry-emulator.tar
docker run --rm -p 18080:18080 --add-host=host.docker.internal:host-gateway \
  --name ndtp-emu ndtp-telemetry-emulator:1.0
```

Далее через REST API эмулятора (порт 18080) настройте устройства и период отправки —
подробности в `docs/Emulator-and-Telematic-Packets-Specification.md`. Эмулятор шлёт NDTP-пакеты
по TCP на `targetHost:targetPort` — укажите хост системы и порт Gateway `19000`.

Для бинарного NDTP-потока переключите декодер Gateway в `.env`:

```dotenv
GATEWAY_DECODER=ndtp
```

и перезапустите: `make down && make up`. Без реализации бинарного парсера (см. README)
используйте JSON Lines — для демонстрации этого достаточно.

## 5. Где увидеть прогнозы

Прогнозы движутся по цепочке и видны в трёх местах:

1. **Дашборд** (http://localhost:8080) — основной интерфейс жюри: карта, ТС, инциденты.
2. **Redis Stream** — сырое хранилище прогнозов:

   ```bash
   docker compose exec redis redis-cli XREVRANGE predictions.v1 + - COUNT 3
   ```

   Каждое событие содержит `tr_id`, `target_stop_id`, `predicted_delta_s` (прогноз
   задержки, сек), `risk_level`, `confidence`, `model_name`.

3. **Swagger Backend** (http://localhost:8000/docs) — REST-эндпоинты со списками
   инцидентов и состояний ТС.

## 6. Где увидеть метрики модели

- **Локальная оценка** — после `make evaluate` результат сравнения MAE модели
  с baseline `cur_dev_s` выводится в консоль; модель должна показывать MAE ниже baseline.
- **Отчёт аудита данных** — `data/interim/audit_report.json` (создаётся `make audit`).
- **Файл решения** — `data/submissions/submission.csv`, формат `sample_id;prediction`,
  готов к загрузке на платформу проверки:

  ```text
  sample_id;prediction
  131672_1767670500;120.0
  122048_1767732000;45.0
  ```

## 7. Типичные проблемы

| Симптом | Причина и решение |
| --- | --- |
| Пакет отправлен, на дашборде ничего нет | `tr_id` нет в `data/runtime/schedule_plan.csv` или нет остановки в окне 10–15 минут. Возьмите `tr_id` из расписания. |
| Прогноз есть в Redis, дашборд не обновляется | Обновите страницу; проверьте, что WebSocket-соединение установлено (вкладка Network в DevTools). |
| `make up` стартует, ML падает | Нет артефакта модели — выполните `make features-train && make train` (раздел 1). |
| Прогнозы помечены `STALE_TELEMETRY` | Время пакета сильно отличается от текущего — подставьте актуальный `timestamp`. |
| Сборка Docker падает с `error getting credentials` | Удалите ключ `credsStore` из `~/.docker/config.json` и перезапустите Docker. |

## 8. Завершение демонстрации

```bash
make down          # остановить контейнеры
```

С полным описанием проекта, обучением модели и генерацией submission см. `README.md`.
