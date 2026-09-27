import csv
import json
import math
import os
import socket
import time
from datetime import datetime, timezone

# --- НАСТРОЙКИ ---
GW_HOST = os.getenv("GW_HOST", "127.0.0.1")
GW_PORT = int(os.getenv("GW_PORT", "19000"))
CSV_FILE = os.getenv("CSV_FILE", "./data/raw/validate/traffic.csv")
SEND_INTERVAL_S = float(os.getenv("SEND_INTERVAL_S", "2"))
RECONNECT_DELAY_S = float(os.getenv("RECONNECT_DELAY_S", "2"))
LOOP_PLAYBACK = os.getenv("LOOP_PLAYBACK", "true").lower() in ("true", "1", "yes")


def safe_float(value, default=None):
    if value is None or str(value).strip() == "":
        return default
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(result):
        return default
    return result


def current_utc():
    return datetime.now(timezone.utc)


def current_utc_timestamp():
    return int(current_utc().timestamp())


def valid_coordinates(lat, lon):
    return (
        lat is not None
        and lon is not None
        and -90.0 <= lat <= 90.0
        and -180.0 <= lon <= 180.0
    )


def forecast_horizon(tr_id):
    checksum = sum(ord(character) for character in str(tr_id))
    return 600 + checksum % 301


def generate_demo_prediction(speed_kmh):
    if speed_kmh is None:
        speed_kmh = 0.0

    if speed_kmh < 3:
        delay_seconds = 240.0
    elif speed_kmh < 5:
        delay_seconds = 190.0
    elif speed_kmh < 10:
        delay_seconds = 145.0
    elif speed_kmh < 15:
        delay_seconds = 105.0
    elif speed_kmh < 25:
        delay_seconds = 55.0
    else:
        delay_seconds = 15.0

    if delay_seconds > 120:
        risk_level = "red"
        network_impact = "Высокое"
        recommendation = "Проверить движение ТС и предупредить диспетчера"
    elif delay_seconds > 60:
        risk_level = "yellow"
        network_impact = "Среднее"
        recommendation = "Контролировать дальнейшее движение"
    else:
        risk_level = "green"
        network_impact = "Низкое"
        recommendation = "Действия не требуются"

    return {
        "predicted_delay_s": delay_seconds,
        "risk_level": risk_level,
        "network_impact": network_impact,
        "recommendation": recommendation,
    }


def connect_gateway():
    while True:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        try:
            sock.connect((GW_HOST, GW_PORT))
            sock.settimeout(None)
            print(f"✅ Подключено к gateway {GW_HOST}:{GW_PORT}")
            return sock
        except OSError as error:
            sock.close()
            print(
                f"⚠️ Gateway недоступен: {error}. "
                f"Повтор через {RECONNECT_DELAY_S} с."
            )
            time.sleep(RECONNECT_DELAY_S)


def send_message(sock, message):
    data = message.encode("utf-8")
    while True:
        try:
            sock.sendall(data)
            return sock
        except OSError as error:
            print(f"⚠️ Соединение потеряно: {error}")
            try:
                sock.close()
            except OSError:
                pass
            sock = connect_gateway()


def build_payload(row):
    tr_id = str(row.get("tr_id", "")).strip()
    lat = safe_float(row.get("lat"))
    lon = safe_float(row.get("lon"))
    speed = safe_float(row.get("speed"), 0.0)
    heading = safe_float(row.get("heading"))
    altitude = safe_float(row.get("alt"))
    location_valid = str(row.get("location_valid", "")).strip().lower() in (
        "true", "1", "yes", "y",
    )

    if not tr_id:
        return None
    if not valid_coordinates(lat, lon):
        return None

    prediction = generate_demo_prediction(speed)
    now = current_utc()
    ts_unix = int(now.timestamp())
    ts_iso = now.isoformat()

    # --- Все варианты имени времени события ---
    # Gateway ищет одно из этих полей; лишние проигнорирует.
    time_fields = {
        "ts": ts_unix,
        "time": ts_unix,
        "tm": ts_unix,
        "fix_time": ts_unix,
        "event_time": ts_iso,
        "timestamp": ts_iso,
        "prediction_time": ts_unix,
        "last_seen_at": ts_iso,
    }

    incident_data = {
        "incident_id": tr_id,
        "tr_id": tr_id,
        "vehicle_number": row.get("vehicle_number") or tr_id,
        "route": row.get("route") or "Не указан",
        "unit_id": row.get("unit_id") or tr_id,
        "packet_id": row.get("packet_id"),
        "lat": lat,
        "lon": lon,
        "alt": altitude,
        "speed": speed,
        "heading": heading,
        "location_valid": True,
        "is_hist_data": False,
        "risk_level": prediction["risk_level"],
        "predicted_delay_s": prediction["predicted_delay_s"],
        "forecast_horizon_s": forecast_horizon(tr_id),
        "network_impact": prediction["network_impact"],
        "reason_text": "Демонстрационный прогноз по потоковой телеметрии",
        "recommendation": prediction["recommendation"],
        "seconds_since_update": 0,
        "source": "csv_telemetry_emulator",
        **time_fields,
    }

    return {
            "type": "prediction",
            "incident": incident_data,
            **time_fields,
            "tr_id": tr_id,
            "unit_id": incident_data["unit_id"],
            "packet_id": incident_data["packet_id"],
            "lat": lat,
            "lon": lon,
            "alt": altitude,
            "speed": speed,
            "heading": heading,
            "location_valid": True,
            "is_hist_data": False,
        }


def validate_csv():
    if not os.path.exists(CSV_FILE):
        raise FileNotFoundError(f"Файл не найден: {CSV_FILE}")

    with open(CSV_FILE, encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        columns = set(reader.fieldnames or [])

    required_columns = {"tr_id", "lat", "lon", "speed"}
    missing_columns = required_columns - columns

    if missing_columns:
        raise ValueError(
            "В CSV отсутствуют обязательные колонки: "
            + ", ".join(sorted(missing_columns))
        )


def replay_csv(sock, total_count):
    sent_count = 0
    skipped_count = 0

    with open(CSV_FILE, encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            payload = build_payload(row)

            if payload is None:
                skipped_count += 1
                continue

            message = (
                json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n"
            )

            sock = send_message(sock, message)
            sent_count += 1
            total_count += 1

            if total_count % 5 == 0:
                incident = payload["incident"]
                print(
                    f"📊 Отправлено: {total_count} | "
                    f"ТС: {incident['tr_id']} | "
                    f"Скорость: {incident['speed']:.1f} км/ч | "
                    f"Прогноз: {incident['predicted_delay_s']:.0f} с | "
                    f"Риск: {incident['risk_level']}"
                )

            if SEND_INTERVAL_S > 0:
                time.sleep(SEND_INTERVAL_S)

    print(
        f"✅ Проход CSV завершён. "
        f"Отправлено: {sent_count}, пропущено: {skipped_count}"
    )
    return sock, total_count


def main():
    try:
        validate_csv()
    except (FileNotFoundError, ValueError) as error:
        print(f"❌ {error}")
        return

    print(f"✅ Файл найден: {CSV_FILE}")
    print(f"🚀 Gateway: {GW_HOST}:{GW_PORT}")
    print(f"⏱ Интервал отправки: {SEND_INTERVAL_S} с.")
    print(f"🔁 Повтор воспроизведения: {LOOP_PLAYBACK}")

    sock = connect_gateway()
    total_count = 0

    try:
        while True:
            sock, total_count = replay_csv(sock, total_count)

            if not LOOP_PLAYBACK:
                break

            print("🔁 Повторное воспроизведение CSV...")

    except KeyboardInterrupt:
        print("\n⚠️ Эмулятор остановлен пользователем.")
    except Exception as error:
        print(f"\n❌ Ошибка эмулятора: {error}")
    finally:
        try:
            sock.close()
        except OSError:
            pass
        print(f"📦 Всего отправлено пакетов: {total_count}")


if __name__ == "__main__":
    main()
