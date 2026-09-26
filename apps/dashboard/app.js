const state = {
  incidents: new Map(),
  riskFilter: "all",
  vehicleFilter: "",
};

// Загружает последние инциденты из Backend.
async function loadIncidents() {
  const response = await fetch("/api/v1/incidents?limit=500");
  if (!response.ok) {
    throw new Error(`Backend returned ${response.status}`);
  }
  const incidents = await response.json();
  incidents.forEach(storeIncident);
  renderDashboard();
}

// Сохраняет или обновляет один инцидент.
function storeIncident(incident) {
  state.incidents.set(incident.incident_id, incident);
}

// Возвращает отфильтрованные инциденты.
function selectVisibleIncidents() {
  const incidents = Array.from(state.incidents.values());
  return incidents
    .filter(selectVisibleIncidentsByRisk)
    .filter(selectVisibleIncidentsByVehicle)
    .sort(compareIncidents);
}

// Проверяет соответствие фильтру риска.
function selectVisibleIncidentsByRisk(incident) {
  return state.riskFilter === "all"
    || incident.risk_level === state.riskFilter;
}

// Проверяет соответствие фильтру транспортного средства.
function selectVisibleIncidentsByVehicle(incident) {
  const query = state.vehicleFilter.trim().toLowerCase();
  return !query || String(incident.tr_id).toLowerCase().includes(query);
}

// Сортирует инциденты по риску и задержке.
function compareIncidents(left, right) {
  const priorities = { red: 3, yellow: 2, green: 1 };
  const riskDifference = (
    priorities[right.risk_level] - priorities[left.risk_level]
  );
  return riskDifference || right.prediction_s - left.prediction_s;
}

// Перерисовывает показатели и таблицу.
function renderDashboard() {
  const incidents = Array.from(state.incidents.values());
  renderMetrics(incidents);
  renderIncidentTable(selectVisibleIncidents());
}

// Обновляет агрегированные показатели.
function renderMetrics(incidents) {
  setText("total-count", incidents.length);
  setText("red-count", countRisk(incidents, "red"));
  setText("yellow-count", countRisk(incidents, "yellow"));
  setText(
    "average-delay",
    `${calculateAverageDelay(incidents)} с`,
  );
}

// Считает инциденты заданного уровня риска.
function countRisk(incidents, riskLevel) {
  return incidents.filter(
    incident => incident.risk_level === riskLevel,
  ).length;
}

// Вычисляет среднюю прогнозируемую задержку.
function calculateAverageDelay(incidents) {
  if (!incidents.length) {
    return 0;
  }
  const sum = incidents.reduce(
    (total, incident) => total + Number(incident.prediction_s),
    0,
  );
  return Math.round(sum / incidents.length);
}

// Заполняет таблицу инцидентами.
function renderIncidentTable(incidents) {
  const table = document.getElementById("incident-table");
  table.replaceChildren(...incidents.map(createIncidentRow));
  document.getElementById("empty-state").hidden = incidents.length > 0;
}

// Создаёт строку одного инцидента.
function createIncidentRow(incident) {
  const row = document.createElement("tr");
  row.innerHTML = `
    <td>${createRiskBadge(incident.risk_level)}</td>
    <td>${escapeHtml(incident.tr_id)}</td>
    <td>${escapeHtml(incident.target_stop_id)}</td>
    <td>${formatSeconds(incident.prediction_s)}</td>
    <td>${formatSignedSeconds(incident.predicted_delta_s)}</td>
    <td>${formatMinutes(incident.forecast_horizon_s)}</td>
    <td>${escapeHtml(incident.reason_text)}</td>
    <td>${escapeHtml(incident.recommendation)}</td>
    <td>${createIncidentActions(incident)}</td>
  `;
  bindIncidentActions(row, incident);
  return row;
}

// Создаёт цветовой индикатор риска.
function createRiskBadge(riskLevel) {
  return `
    <span class="risk risk-${escapeHtml(riskLevel)}">
      ${translateRisk(riskLevel)}
    </span>
  `;
}

// Создаёт кнопки действий с инцидентом.
function createIncidentActions(incident) {
  if (incident.status === "closed") {
    return '<span class="action-complete">Закрыт</span>';
  }
  const acknowledge = incident.acknowledged
    ? '<span class="action-complete">Принято</span>'
    : `<button class="ack-button" type="button">Принять</button>`;
  return `
    <div class="actions">
      ${acknowledge}
      <button class="close-button" type="button">Закрыть</button>
    </div>
  `;
}

// Подключает обработчики кнопок строки.
function bindIncidentActions(row, incident) {
  const acknowledgeButton = row.querySelector(".ack-button");
  const closeButton = row.querySelector(".close-button");
  acknowledgeButton?.addEventListener(
    "click",
    () => changeIncident(incident.incident_id, "ack"),
  );
  closeButton?.addEventListener(
    "click",
    () => changeIncident(incident.incident_id, "close"),
  );
}

// Выполняет действие над инцидентом.
async function changeIncident(incidentId, action) {
  const encoded = encodeURIComponent(incidentId);
  const response = await fetch(
    `/api/v1/incidents/${encoded}/${action}`,
    { method: "POST" },
  );
  if (!response.ok) {
    throw new Error(`Incident action failed: ${response.status}`);
  }
  storeIncident(await response.json());
  renderDashboard();
}

// Открывает WebSocket для online-обновлений.
function connectWebSocket() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(
    `${protocol}://${location.host}/api/v1/stream`,
  );
  socket.addEventListener("open", () => setConnectionStatus(true));
  socket.addEventListener("message", handleSocketMessage);
  socket.addEventListener("close", scheduleReconnect);
  socket.addEventListener("error", () => socket.close());
}

// Обрабатывает WebSocket-событие.
function handleSocketMessage(event) {
  const message = JSON.parse(event.data);
  if (!message.payload) {
    return;
  }
  storeIncident(message.payload);
  renderDashboard();
}

// Планирует повторное подключение к WebSocket.
function scheduleReconnect() {
  setConnectionStatus(false);
  window.setTimeout(connectWebSocket, 2000);
}

// Обновляет индикатор соединения.
function setConnectionStatus(connected) {
  const element = document.getElementById("connection-status");
  element.textContent = connected ? "Онлайн" : "Нет соединения";
  element.className = connected
    ? "connection connection-online"
    : "connection connection-offline";
}

// Регистрирует фильтры и кнопку обновления.
function registerControls() {
  document.getElementById("risk-filter").addEventListener(
    "change",
    event => {
      state.riskFilter = event.target.value;
      renderDashboard();
    },
  );
  document.getElementById("vehicle-filter").addEventListener(
    "input",
    event => {
      state.vehicleFilter = event.target.value;
      renderDashboard();
    },
  );
  document.getElementById("refresh-button").addEventListener(
    "click",
    () => loadIncidents().catch(console.error),
  );
}

// Переводит уровень риска.
function translateRisk(riskLevel) {
  return {
    red: "Высокий",
    yellow: "Средний",
    green: "Низкий",
  }[riskLevel] || "Неизвестно";
}

// Форматирует количество секунд.
function formatSeconds(value) {
  return `${Math.round(Number(value))} с`;
}

// Форматирует изменение задержки со знаком.
function formatSignedSeconds(value) {
  const number = Math.round(Number(value));
  return `${number > 0 ? "+" : ""}${number} с`;
}

// Форматирует горизонт в минутах.
function formatMinutes(value) {
  return `${Math.round(Number(value) / 60)} мин`;
}

// Безопасно задаёт текст DOM-элемента.
function setText(identifier, value) {
  document.getElementById(identifier).textContent = String(value);
}

// Экранирует значение перед вставкой в HTML.
function escapeHtml(value) {
  const element = document.createElement("div");
  element.textContent = String(value ?? "");
  return element.innerHTML;
}

// Запускает диспетчерский интерфейс.
async function startDashboard() {
  registerControls();
  connectWebSocket();
  await loadIncidents();
}

startDashboard().catch(console.error);
