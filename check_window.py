import csv
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

now = datetime.now(ZoneInfo("Europe/Moscow")).astimezone(ZoneInfo("UTC"))
sec_now = now.hour * 3600 + now.minute * 60 + now.second

with open("data/runtime/schedule_plan.csv") as f:
    rows = list(csv.DictReader(f))

bad = set()
parsed = 0
hits = {}
for r in rows:
    raw = (r.get("time_begin") or "").strip()
    t = None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M:%S"):
        try:
            t = datetime.strptime(raw, fmt)
            break
        except ValueError:
            continue
    if t is None:
        if raw:
            bad.add(raw[:20])
        continue
    parsed += 1
    sec_t = t.hour * 3600 + t.minute * 60 + t.second
    delta = sec_t - sec_now
    if 10 * 60 < delta <= 15 * 60:
        hits.setdefault(r["tr_id"], []).append(
            (r["time_begin"][11:16], r.get("tt_action_item_id", ""))
        )

print("Текущее время (МСК):", now.astimezone(ZoneInfo("Europe/Moscow")).strftime("%H:%M:%S"))
print("Распознано строк:", parsed, "| нераспознано:", len(rows) - parsed)
if bad:
    print("Примеры плохих значений time_begin:", sorted(bad)[:5])
print("Окно поиска:", (now + timedelta(minutes=10)).strftime("%H:%M"),
      "-", (now + timedelta(minutes=15)).strftime("%H:%M"))
if not hits:
    print("Окно пустое — перезапусти скрипт через минуту")
for tr_id, stops in sorted(hits.items()):
    print(tr_id, "->", stops)
