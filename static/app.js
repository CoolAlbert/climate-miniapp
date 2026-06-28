const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();

const roomsEl = document.querySelector("#rooms");
const roomTabsEl = document.querySelector("#room-tabs");
const summaryEl = document.querySelector("#summary");
const updatedEl = document.querySelector("#updated");
const errorEl = document.querySelector("#error");
const refreshButton = document.querySelector("#refresh");
const telegramInitData = tg?.initData ?? "";

let currentPayload = null;
let selectedRoom = "all";

const formatters = {
  temperature: (value) => (value == null ? "—" : `${value}°C`),
  humidity: (value) => (value == null ? "—" : `${value}%`),
  pressure: (value) => (value == null ? "—" : `${value} мм`),
  battery: (value) => (value == null ? "—" : `${value}%`),
};

function metric(label, value, note = "") {
  return `
    <article class="metric">
      <div class="metric-label">${label}</div>
      <div class="metric-value">${value}</div>
      ${note ? `<div class="metric-note">${note}</div>` : ""}
    </article>
  `;
}

function valueBlock(kind, label, value) {
  return `
    <div class="value ${kind}">
      <div class="label">${label}</div>
      <div class="reading">${value}</div>
    </div>
  `;
}

function average(values) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}

function roomAverages(room) {
  const temps = room.devices.map((device) => device.temperature).filter((value) => value != null);
  const humidity = room.devices.map((device) => device.humidity).filter((value) => value != null);
  return {
    temperature: average(temps),
    humidity: average(humidity),
  };
}

function roomMeta(room) {
  const avg = roomAverages(room);
  const temp = avg.temperature == null ? "—" : `${avg.temperature.toFixed(1)}°`;
  const hum = avg.humidity == null ? "—" : `${avg.humidity.toFixed(0)}%`;
  return `${temp} · ${hum}`;
}

function comfort(device) {
  const temp = device.temperature;
  const humidity = device.humidity;
  if (temp == null && humidity == null) return { label: "Нет оценки", level: "" };
  const tempOk = temp == null || (temp >= 21 && temp <= 25.5);
  const humidityOk = humidity == null || (humidity >= 35 && humidity <= 60);
  if (tempOk && humidityOk) return { label: "Комфортно", level: "good" };
  if (temp != null && temp > 25.5) return { label: "Тепло", level: "warn" };
  if (temp != null && temp < 21) return { label: "Прохладно", level: "warn" };
  if (humidity != null && humidity > 60) return { label: "Влажно", level: "warn" };
  return { label: "Сухо", level: "warn" };
}

function visibleRooms(payload) {
  if (selectedRoom === "all") return payload.rooms;
  return payload.rooms.filter((room) => room.name === selectedRoom);
}

function renderTabs(payload) {
  const tabs = [
    { key: "all", label: "Все" },
    ...payload.rooms.map((room) => ({ key: room.name, label: room.name })),
  ];

  roomTabsEl.innerHTML = tabs.map((tab) => `
    <button class="tab" type="button" data-room="${tab.key}" aria-selected="${selectedRoom === tab.key}">
      ${tab.label}
    </button>
  `).join("");
}

function render(payload) {
  currentPayload = payload;
  const devices = payload.rooms.flatMap((room) => room.devices);
  const temps = devices.map((device) => device.temperature).filter((value) => value != null);
  const humidity = devices.map((device) => device.humidity).filter((value) => value != null);
  const pressure = devices.map((device) => device.pressure).filter((value) => value != null);
  const avgTemp = average(temps);
  const avgHumidity = average(humidity);
  const avgPressure = average(pressure);

  summaryEl.innerHTML = [
    metric("Температура", avgTemp == null ? "—" : `${avgTemp.toFixed(1)}°C`, `${temps.length} источника`),
    metric("Влажность", avgHumidity == null ? "—" : `${avgHumidity.toFixed(1)}%`),
    metric("Давление", avgPressure == null ? "—" : `${avgPressure.toFixed(0)} мм`),
  ].join("");

  renderTabs(payload);

  roomsEl.innerHTML = visibleRooms(payload).map((room) => `
    <section class="room">
      <h2>
        <span>${room.name}</span>
        <span class="room-meta">${roomMeta(room)}</span>
      </h2>
      ${room.devices.map((device) => {
        const status = comfort(device);
        return `
          <article class="device">
            <div class="device-head">
              <div>
                <div class="device-name">${device.name}</div>
                <div class="device-type">${device.type?.replace("devices.types.", "") ?? ""}</div>
              </div>
              <div class="comfort ${status.level}">${status.label}</div>
            </div>
            <div class="values">
              ${valueBlock("temp", "Температура", formatters.temperature(device.temperature))}
              ${valueBlock("humidity", "Влажность", formatters.humidity(device.humidity))}
              ${valueBlock("pressure", "Давление", formatters.pressure(device.pressure))}
              ${valueBlock("battery", "Батарея", formatters.battery(device.battery))}
            </div>
          </article>
        `;
      }).join("")}
    </section>
  `).join("");

  updatedEl.textContent = `Обновлено ${new Date(payload.updatedAt * 1000).toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  })}`;
}

async function loadClimate() {
  refreshButton.disabled = true;
  errorEl.hidden = true;
  try {
    const response = await fetch("/api/climate", {
      cache: "no-store",
      headers: telegramInitData ? { "X-Telegram-Init-Data": telegramInitData } : {},
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    render(await response.json());
  } catch (error) {
    errorEl.hidden = false;
    errorEl.textContent = `Не удалось обновить данные: ${error.message}`;
  } finally {
    refreshButton.disabled = false;
  }
}

roomTabsEl.addEventListener("click", (event) => {
  const tab = event.target.closest(".tab");
  if (!tab || !currentPayload) return;
  selectedRoom = tab.dataset.room;
  render(currentPayload);
});

refreshButton.addEventListener("click", loadClimate);
loadClimate();
