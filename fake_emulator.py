import socket
import time
import csv
import json
import os
from datetime import datetime

# --- НАСТРОЙКИ ---
GW_HOST = '127.0.0.1'
GW_PORT = 19000
CSV_FILE = './data/raw/validate/traffic.csv'

def safe_float(value, default=0.0):
    """
    Безопасно конвертирует значение в float.
    Если строка пустая или не число — возвращает default.
    """
    if value is None or value.strip() == '':
        return default
    try:
        return float(value)
    except ValueError:
        print(f"⚠️ Не удалось конвертировать '{value}' в float. Используем {default}.")
        return default

def parse_event_time(time_str):
    """
    Преобразует строку даты в Unix timestamp.
    Поддерживает форматы с микросекундами и без.
    """
    if not time_str:
        return 0
    
    fmt = '%Y-%m-%d %H:%M:%S.%f'
    try:
        dt = datetime.strptime(time_str, fmt)
        return int(dt.timestamp())
    except ValueError:
        fmt_fallback = '%Y-%m-%d %H:%M:%S'
        try:
            dt = datetime.strptime(time_str, fmt_fallback)
            return int(dt.timestamp())
        except ValueError:
            print(f"⚠️ Не удалось распарсить время: {time_str}. Возвращаем 0.")
            return 0

def main():
    if not os.path.exists(CSV_FILE):
        print(f"❌ Файл не найден: {CSV_FILE}")
        return
    print(f"✅ Файл найден: {CSV_FILE}")

    print(f"🚀 Подключаемся к gateway на {GW_HOST}:{GW_PORT}...")
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((GW_HOST, GW_PORT))
        print("✅ Успешное подключение к gateway!")
        print("📡 Начинаем эмуляцию потока (Ctrl+C для остановки)...\n")
    except ConnectionRefusedError:
        print("\n❌ Ошибка: Gateway не отвечает на порту 19000.")
        return
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return

    with open(CSV_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        count = 0
        skipped_empty = 0
        
        for row in reader:
            # Проверка на пустые координаты (основная причина ошибки)
            lat = safe_float(row.get('lat', ''))
            lon = safe_float(row.get('lon', ''))
            
            # Если и широта, и долгота пустые — такую точку смысла слать нет, пропускаем
            if lat == 0.0 and lon == 0.0 and (row.get('lat') == '' or row.get('lon') == ''):
                skipped_empty += 1
                continue

            try:
                payload = {
                    "tr_id": row['tr_id'],
                    "event_time": parse_event_time(row['event_time']),
                    "lat": lat,
                    "lon": lon,
                    "speed": safe_float(row.get('speed', '0')),
                    "location_valid": row.get('location_valid', 'false').lower() == 'true',
                    "source": "fake_emulator"
                }
            except KeyError as e:
                print(f"⚠️ Пропущена строка (нет колонки {e}).")
                continue
            
            message = json.dumps(payload) + "\n"
            
            try:
                sock.sendall(message.encode('utf-8'))
                count += 1
            except Exception as e:
                print(f"Ошибка отправки: {e}")
                break
            
            # Имитация потока: 1 пакет каждые 3 секунды
            time.sleep(3.0)
            
            if count % 10 == 0:
                print(f"📊 Отправлено пакетов: {count} (последний ID: {row['tr_id']})")

    print(f"\n🏁 Конец файла. Эмулятор завершил работу.")
    print(f"✅ Всего отправлено: {count} пакетов.")
    if skipped_empty > 0:
        print(f"⚠️ Пропущено строк из-за отсутствия координат: {skipped_empty}")
    
    sock.close()

if __name__ == "__main__":
    main()
