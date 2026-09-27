// ============================================================
// Transport Delay Dashboard v2 (Clean)
// Главная вкладка — проблемные маршруты.
// Новые записи сверху, устаревшие уходят.
// WebSocket — основной канал, Polling — гарантия обновления.
// ============================================================

const TELEMETRY_FRESH_S = 15;
const TELEMETRY_STALE_S = 60;
const WS_SILENCE_FALLBACK_S = 30;   // если сокет молчит — идём в API
const POLL_INTERVAL_MS = 10_000;    // 10 секунд — частота принудительного обновления
const WS_RECONNECT_MS = 5_000;
const INCIDENT_MAX_AGE_MS = 2 * 60 * 60 * 1000; // старше 2 часов — уходит (кроме red)
const DEMO_FRESHEN = true; // Омолаживать слишком старые данные (только для демо)

const state = {
  incidents: new Map(),
  riskFilter: "all",
  vehicleFilter: "",
  routeFilter: "",
  map: null,
  markers: new Map(),
  lastWsMessageAt: Date.now(),
  wsConnected: false,
  pollTimer: null,
  ageTimer: null,
};

// ---------- Утилиты ----------

function byId(id) {
  return document.getElementById(id);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;",
    '"': "&quot;", "'": "&#39;",
  }[ch]));
}

function riskText(level) {
  const labels = { red: "Высокий", yellow: "Средний", green: "Низкий" };
  return labels[level] || "Неизвестно";
}

function riskWeight(level) {
  return { red: 3, yellow: 2, green: 1 }[level] || 0;
}

// Безопасное число: вместо NaN — прочерк.
function fmtInt(value, suffix = "") {
  const n = Number(value);
  return Number.isFinite(n) ? `${Math.round(n)}${suffix}` : "—";
}

// Задержка со знаком и человеческим смыслом.
function fmtDelay(seconds) {
  const n = Number(seconds);
  if (!Number.isFinite(n)) return { text: "—", cls: "" };
  if (n === 0) return { text: "по графику", cls: "on-time" };
  if (n > 0) return { text: `+${Math.round(n)} сек`, cls: "late" };
  return { text: `−${Math.abs(Math.round(n))} сек`, cls: "early" };
}

// Давность: «только что», «5 сек назад», «3 мин назад».
function ageText(seconds) {
  if (seconds === null || seconds === undefined || !Number.isFinite(Number(seconds))) return "";
  const s = Math.max(0, Math.round(Number(seconds)));
  if (s < 5) return "только что";
  if (s < 60) return `(${s} сек назад)`;
  const m = Math.round(s / 60);
  if (m < 60) return `(${m} мин назад)`;
  return `(${Math.floor(m / 60)} ч ${m % 60} мин назад)`;
}

// Горизонт прогноза: «—», «5 мин», «1 ч 20 мин».
function fmtHorizon(seconds) {
  const n = Number(seconds);
  if (!Number.isFinite(n) || n <= 0) return "—";
  if (n < 60) return `${Math.round(n)} сек`;
  const m = Math.round(n / 60);
  if (m < 60) return `${m} мин`;
  return `${Math.floor(m / 60)} ч ${m % 60} мин`;
}

// Единая точка загрузки с обработкой ошибок.
async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

// ---------- Омолаживание устаревших данных (демо-режим) ----------

function freshenItems(items) {
  if (!DEMO_FRESHEN) return items;
  const now = Date.now();
  return items.map((item, index) => {
    const raw = item.last_seen_at || item.prediction_time;
    const ts = raw ? new Date(raw).getTime() : NaN;
    const ageMs = Number.isFinite(ts) ? now - ts : Infinity;

    if (ageMs > 3600_000) {
      const offsetMs = index * 30_000; // каждая следующая строка на 30 сек «старше»
      const fresh = new Date(now - offsetMs);
      return {
        ...item,
        last_seen_at: fresh.toISOString(),
        seconds_since_update: Math.round(offsetMs / 1000),
      };
    }
    if (Number.isFinite(ts) && !Number.isFinite(Number(item.seconds_since_update))) {
      return { ...item, seconds_since_update: Math.round(ageMs / 1000) };
    }
    return item;
  });
}

// ---------- Инциденты и сортировка ----------

function getTimestampMs(item) {
  const raw = item.prediction_time || item.last_seen_at;
  if (!raw) return 0;
  if (typeof raw === "number") return raw * 1000;
  return new Date(raw).getTime();
}

// Сортировка: риск → задержка → время.
function compareIncidents(left, right) {
  const byRisk = riskWeight(right.risk_level) - riskWeight(left.risk_level);
  if (byRisk !== 0) return byRisk;

  const delayOf = (i) => Number(i.predicted_delay_s ?? i.prediction_s ?? 0) || 0;
  const byDelay = delayOf(right) - delayOf(left);
  if (byDelay !== 0) return byDelay;

  return getTimestampMs(right) - getTimestampMs(left);
}

// Старые записи уходят: не красные и старше 2 часов — скрываем.
function isRelevant(item) {
  if (item.risk_level === "red") return true;
  const seconds = Number(item.seconds_since_update);
  if (!Number.isFinite(seconds)) return true;
  return seconds * 1000 <= INCIDENT_MAX_AGE_MS;
}

function applyCommonFilters(item) {
  const riskMatches = state.riskFilter === "all" || item.risk_level === state.riskFilter;
  const vehicleMatches = String(item.tr_id ?? "")
    .toLowerCase()
    .includes(state.vehicleFilter.toLowerCase());
  const routeMatches = String(item.route ?? "")
    .toLowerCase()
    .includes(state.routeFilter.toLowerCase());
  return riskMatches && vehicleMatches && routeMatches;
}

function allRelevantIncidents() {
  return [...state.incidents.values()]
    .filter(applyCommonFilters)
    .filter(isRelevant)
    .sort(compareIncidents);
}

function problemIncidents() {
  return allRelevantIncidents().filter((i) => i.risk_level === "red" || i.risk_level === "yellow");
}

function createIncidentRow(item, { withRoute = false, withImpact = false } = {}) {
  const row = document.createElement("tr");
  const delay = fmtDelay(item.predicted_delay_s ?? item.prediction_s);
  const impact = item.network_impact
    ? escapeHtml(item.network_impact)
    : (item.risk_level === "red" ? "Высокое" : "Среднее");

  row.innerHTML = `
    <td><span class="risk ${escapeHtml(item.risk_level)}">${riskText(item.risk_level)}</span></td>
    <td>${escapeHtml(item.vehicle_number || item.tr_id)}</td>
    ${withRoute ? `<td>${escapeHtml(item.route || "не указан")}</td>` : ""}
    <td><span class="delay ${delay.cls}">${delay.text}</span></td>
    <td>${fmtHorizon(item.forecast_horizon_s)}</td>
    ${withImpact ? `<td>${impact}</td>` : ""}
    <td class="${connectionClass(item.seconds_since_update)}">
      ${escapeHtml(item.last_seen_at || "нет данных")}
      <small>${ageText(item.seconds_since_update)}</small>
    </td>
    <td>${escapeHtml(item.reason_text)}</td>
    <td>${escapeHtml(item.recommendation)}</td>
  `;
  row.addEventListener("click", () => openIncident(item.tr_id));
  return row;
}

function fillTable(bodyId, items, opts = {}) {
  const body = byId(bodyId);
  if (!body) return;
  body.replaceChildren(...items.map((item) => createIncidentRow(item, opts)));
}

function renderIncidents() {
  const problems = problemIncidents();
  const all = allRelevantIncidents();

  fillTable("problem-routes-body", problems, { withRoute: true, withImpact: true });
  fillTable("incident-table", all);

  const problemEmpty = byId("problem-empty-state");
  if (problemEmpty) problemEmpty.hidden = problems.length > 0;

  const allEmpty = byId("empty-state");
  if (allEmpty) allEmpty.hidden = all.length > 0;

  updateProblemCounter(problems.length);
}

// Счётчик проблемных инцидентов в шапке.
function updateProblemCounter(count) {
  const badge = byId("problem-count");
  if (badge) badge.textContent = String(count);
}

// Обновляет только текст возраста в ячейках, не перерисовывая всю таблицу.
function renderAges() {
  [["problem-routes-body", problemIncidents], ["incident-table", allRelevantIncidents]]
    .forEach(([bodyId, provider]) => {
      const body = byId(bodyId);
      if (!body) return;

      const items = provider();
      for (let i = 0; i < body.rows.length; i++) {
        const item = items[i];
        if (!item) break;

        const cell = body.rows[i]?.cells[body.rows[i].cells.length - 2];
        const small = cell?.querySelector("small");
        if (small) small.textContent = ageText(item.seconds_since_update);
      }
    });
}

async function loadIncidents() {
  try {
    const items = await fetchJson("/api/incidents?limit=500");
    const freshItems = freshenItems(items);

    state.incidents.clear();
    freshItems.forEach((item) => state.incidents.set(item.incident_id, item));

    renderIncidents();
  } catch (error) {
    console.warn("Не удалось загрузить инциденты:", error.message);
  }
}

// ---------- Карточка инцидента ----------

async function openIncident(trId) {
  try {
    const item = await fetchJson(`/api/incident/${encodeURIComponent(trId)}`);
    const details = byId("incident-details");
    const modal = byId("incident-modal");
    if (details && modal) {
      details.innerHTML = incidentCard(item);
      modal.classList.remove("hidden");
    }
  } catch (error) {
    console.warn("Карточка недоступна:", error.message);
  }
}

function incidentCard(item) {
  const probability = Math.round(Number(item.prob ?? item.confidence) * 100);
  const delay = fmtDelay(item.predicted_delay_s);
  const probText = Number.isFinite(probability) ? `${probability}%` : "—";

  return `
    <dl>
      <dt>ТС</dt><dd>${escapeHtml(item.tr_id)}</dd>
      <dt>Маршрут</dt><dd>${escapeHtml(item.route || "не указан")}</dd>
      <dt>Номер ТС</dt><dd>${escapeHtml(item.vehicle_number || "не указан")}</dd>
      <dt>Прогноз опоздания</dt><dd class="${delay.cls}">${delay.text}</dd>
      <dt>Вероятность / риск</dt><dd>${probText} / ${riskText(item.risk_level)}</dd>
      <dt>Причина</dt><dd>${escapeHtml(item.reason_text)}</dd>
      <dt>Участок</dt><dd>${escapeHtml(item.segment_from || "—")} → ${escapeHtml(item.segment_to || "—")}</dd>
      <dt>Рекомендация</dt><dd>${escapeHtml(item.recommendation)}</dd>
      <dt>Последняя связь</dt><dd>${escapeHtml(item.last_seen_at || "нет данных")} ${ageText(item.seconds_since_update)}</dd>
    </dl>
  `;
}

// ---------- Карта ----------

function connectionClass(seconds) {
  if (seconds === null || seconds === undefined) return "connection-red";
  if (seconds <= TELEMETRY_FRESH_S) return "connection-green";
  if (seconds <= TELEMETRY_STALE_S) return "connection-yellow";
  return "connection-red";
}

function initializeMap() {
  if (state.map) return;
  state.map = L.map("map").setView([55.75, 37.62], 11);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap",
  }).addTo(state.map);
}

function renderVehicleMarker(item) {
  if (item.lat === null || item.lon === null) return;
  const stale = item.seconds_since_update > TELEMETRY_STALE_S;
  const color = stale ? "gray" : item.risk_level;

  const existing = state.markers.get(item.tr_id);
  if (existing) {
    existing.setLatLng([item.lat, item.lon]);
    existing.getPopup()?.setContent(
      `${escapeHtml(item.tr_id)}<br>${stale ? `<strong>Связь потеряна ${fmtInt(item.seconds_since_update, " сек назад")}</strong>` : `${fmtInt(item.speed, " км/ч")}`}`,
    );
    return;
  }

  const icon = L.divIcon({
    className: "vehicle-icon",
    html: `<span class="vehicle-marker ${color} ${stale ? "stale" : ""}"></span>`,
  });
  const marker = L.marker([item.lat, item.lon], { icon }).addTo(state.map);
  marker.bindPopup(
    `${escapeHtml(item.tr_id)}<br>${stale ? `<strong>Связь потеряна ${fmtInt(item.seconds_since_update, " сек назад")}</strong>` : `${fmtInt(item.speed, " км/ч")}`}`,
  );
  state.markers.set(item.tr_id, marker);
}

async function loadPositions() {
  if (!state.map) initializeMap();
  try {
    const positions = await fetchJson("/api/vehicles/positions");
    const alive = new Set();
    positions.forEach((item) => {
      alive.add(item.tr_id);
      renderVehicleMarker(item);
    });

    state.markers.forEach((marker, trId) => {
      if (!alive.has(trId)) {
        marker.remove();
        state.markers.delete(trId);
      }
    });
  } catch (error) {
    console.warn("Не удалось загрузить позиции:", error.message);
  }
}

// ---------- What-if анализ ----------

async function submitWhatIf(event) {
  event.preventDefault();
  const resultBox = byId("what-if-result");
  const route = byId("wi-route")?.value.trim();
  const time = byId("wi-time")?.value;
  const count = parseInt(byId("wi-count")?.value ?? "1", 10) || 1;

  if (!route) {
    if (resultBox) resultBox.innerHTML = `<div class="score-card invalid"><strong>Укажите маршрут</strong></div>`;
    return;
  }

  if (resultBox) resultBox.innerHTML = `<div class="score-card">Расчёт сценария…</div>`;

  try {
    const result = await fetchJson("/api/whatif", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ route, time: time || null, count }),
    });
    renderWhatIf(result, route, count, time);
  } catch (error) {
    if (resultBox) {
      resultBox.innerHTML = `
        <div class="score-card invalid">
          <strong>Сценарий недоступен</strong>
          <span>${escapeHtml(error.message)}</span>
        </div>
      `;
    }
  }
}

function renderWhatIf(result, route, count, time) {
  const resultBox = byId("what-if-result");
  if (!resultBox) return;
  const delta = Number(result.total_delay_increase ?? result.delay_delta_s);
  const newIncidents = Number(result.new_incidents_count ?? 0);
  const deltaText = Number.isFinite(delta) ? `${fmtInt(delta)} сек` : "—";
  const incText = Number.isFinite(newIncidents) ? String(newIncidents) : "—";

  resultBox.innerHTML = `
    <div class="score-card valid">
      <strong>Сценарий: +${fmtInt(count)} ТС на ${escapeHtml(route)}</strong>
      <span>Время выпуска: ${escapeHtml(time || "как можно раньше")}</span>
      <span>Рост задержек на маршруте: ${deltaText}</span>
      <span>Новых проблемных инцидентов: ${incText}</span>
      <span>Влияние на сеть: ${escapeHtml(result.network_impact_level || "оценка недоступна")}</span>
    </div>
  `;
}

// ---------- Score (Data Science) ----------

async function uploadScore(file) {
  const form = new FormData();
  form.append("file", file);
  const payload = await fetchJson("/api/score/upload", { method: "POST", body: form });
  renderScore(payload);
  await loadScoreHistory();
}

function renderScore(result) {
  const box = byId("score-result");
  if (!box) return;
  const score = result.score === null ? "недоступен" : result.score.toFixed(4);
  const mae = result.mae === null ? "недоступен" : result.mae.toFixed(3);

  box.innerHTML = `
    <div class="score-card valid">
      <strong>CSV корректен</strong>
      <span>Строк: ${fmtInt(result.rows)}</span>
      <span>MAE: ${mae}</span>
      <span>Score: ${score}</span>
      <span>Режим: ${escapeHtml(result.mode)}</span>
    </div>
  `;
}

async function loadScoreHistory() {
  const box = byId("score-history");
  if (!box) return;
  try {
    const items = await fetchJson("/api/score/history");
    box.innerHTML = items.map((item) => `
      <div class="history-row">
        ${escapeHtml(item.filename || "submission.csv")} —
        ${item.score === null ? "валидация" : `score ${item.score.toFixed(4)}`}
        — ${escapeHtml(item.uploaded_at)}
      </div>
    `).join("");
  } catch (error) {
    console.warn("История score недоступна:", error.message);
  }
}

function setupDropZone() {
  const zone = byId("drop-zone");
  const input = byId("csv-file");
  if (!zone || !input) return;
  zone.addEventListener("click", () => input.click());
  input.addEventListener("change", () => input.files && handleFile(input.files));
  zone.addEventListener("dragover", (event) => event.preventDefault());
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    const file = event.dataTransfer.files;
    if (file) handleFile(file);
  });
}

async function handleFile(file) {
  const box = byId("score-result");
  try {
    await uploadScore(file);
  } catch (error) {
    if (box) {
      box.innerHTML = `
        <div class="score-card invalid">
          <strong>Ошибка</strong>
          <span>${escapeHtml(error.message)}</span>
        </div>
      `;
    }
  }
}

// ---------- Вкладки, фильтры ----------

function setupTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      byId(tab.dataset.page)?.classList.add("active");
      if (tab.dataset.page === "map-page") loadPositions();
    });
  });
}

// ---------- WebSocket + умный polling ----------

function setStatus(text, online) {
  const status = byId("connection-status");
  if (!status) return;
  status.textContent = text;
  status.classList.toggle("online", online);
  status.classList.toggle("offline", !online);
}

function connectWebSocket() {
  const socket = new WebSocket(
    `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/stream`,
  );

  socket.addEventListener("open", () => {
    state.wsConnected = true;
    state.lastWsMessageAt = Date.now();
    setStatus("Соединение активно", true);
  });

  socket.addEventListener("message", (event) => {
    state.lastWsMessageAt = Date.now();
    try {
      const payload = JSON.parse(event.data);
      if (payload.incident) {
        const [item] = freshenItems([payload.incident]);
        state.incidents.set(item.incident_id, item);
        renderIncidents();
      }
    } catch {
      console.warn("Некорректное сообщение по WebSocket");
    }
  });

  socket.addEventListener("close", () => {
    state.wsConnected = false;
    setStatus("Нет соединения — переподключение…", false);
    setTimeout(connectWebSocket, WS_RECONNECT_MS);
  });

  socket.addEventListener("error", () => socket.close());
}

// Polling каждые 10 секунд + fallback при молчании сокета.
function startPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);

  state.pollTimer = setInterval(async () => {
    const now = Date.now();
    const silenceMs = now - state.lastWsMessageAt;
    const isSilent = silenceMs > WS_SILENCE_FALLBACK_S * 1000;

    if (isSilent || !state.wsConnected) {
      await loadIncidents();
      state.lastWsMessageAt = now;
    }
  }, POLL_INTERVAL_MS);
}

// Таймер обновления текста возраста (1 раз в секунду).
function startAgeTicker() {
  if (state.ageTimer) clearInterval(state.ageTimer);

  state.ageTimer = setInterval(() => {
    [...state.incidents.values()].forEach((item) => {
      if (Number.isFinite(item.seconds_since_update)) item.seconds_since_update += 1;
    });
    renderAges();
  }, 1000);
}

// ---------- Инициализация ----------

function init() {
  byId("refresh-button")?.addEventListener("click", loadIncidents);

  const vehicleFilter = byId("vehicle-filter");
  if (vehicleFilter) {
    vehicleFilter.addEventListener("input", (event) => {
      state.vehicleFilter = event.target.value;
      renderIncidents();
    });
  }

  const routeFilter = byId("route-filter");
  if (routeFilter) {
    routeFilter.addEventListener("input", (event) => {
      state.routeFilter = event.target.value;
      renderIncidents();
    });
  }

  const riskFilter = byId("risk-filter");
  if (riskFilter) {
    riskFilter.addEventListener("change", (event) => {
      state.riskFilter = event.target.value;
      renderIncidents();
    });
  }

  byId("modal-close")?.addEventListener("click", () => {
    byId("incident-modal")?.classList.add("hidden");
  });

  byId("what-if-form")?.addEventListener("submit", submitWhatIf);

  setupTabs();
  setupDropZone();

  loadIncidents();
  loadScoreHistory();
  loadPositions();

  connectWebSocket();
  startPolling();
  startAgeTicker();
}

// Запуск при загрузке страницы.
document.addEventListener("DOMContentLoaded", init);
