const $ = (id) => document.getElementById(id);

const THEME_KEY = "zt-theme";

function applyTheme(theme) {
  const body = document.body;
  body.classList.remove("theme-light", "theme-dark");
  body.classList.add(theme === "dark" ? "theme-dark" : "theme-light");
  const btn = $("themeToggle");
  if (btn) {
    btn.textContent = theme === "dark" ? "Light mode" : "Dark mode";
  }
}

function initTheme() {
  let theme = null;
  try {
    theme = window.localStorage.getItem(THEME_KEY);
  } catch {
    theme = null;
  }
  if (theme !== "light" && theme !== "dark") {
    const prefersDark =
      window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches;
    theme = prefersDark ? "dark" : "light";
  }
  applyTheme(theme);
  const btn = $("themeToggle");
  if (btn) {
    btn.addEventListener("click", () => {
      const next = document.body.classList.contains("theme-dark")
        ? "light"
        : "dark";
      applyTheme(next);
      try {
        window.localStorage.setItem(THEME_KEY, next);
      } catch {
        // ignore
      }
    });
  }
}

function clamp(n, a, b) {
  return Math.max(a, Math.min(b, n));
}

function trustPct(trustScore01) {
  return Math.round(clamp(trustScore01, 0, 1) * 100);
}

function riskLevelFromTrust(t) {
  if (t >= 0.7) return { label: "Low", cls: "badge--low" };
  if (t >= 0.4) return { label: "Medium", cls: "badge--med" };
  return { label: "High", cls: "badge--high" };
}

function actionFromDecision(decision) {
  if (decision === "allow") return { label: "Allow", cls: "badge--allow" };
  if (decision === "challenge") return { label: "Restrict", cls: "badge--restrict" };
  return { label: "Block", cls: "badge--block" };
}

function locationLabelFromContext(ctx) {
  if (ctx && ctx.location && ctx.location !== "Unknown") {
    return ctx.location;
  }
  if (ctx && ctx.location_risk) {
    const r = ctx.location_risk;
    if (r <= 0.3) return "Delhi";
    if (r <= 0.7) return "Mumbai";
  }
  return "Unknown";
}

function deviceTypeFromContext(ctx) {
  if (ctx && ctx.device_type && ctx.device_type !== "Unknown") {
    return ctx.device_type;
  }
  if (ctx && ctx.device_id) {
    const id = ctx.device_id.toLowerCase();
    if (id.includes("laptop") || id.includes("lap")) return "Laptop";
    if (id.includes("android") || id.includes("mobile")) return "Android";
    if (id.includes("desktop") || id.includes("pc")) return "Desktop";
    if (id.includes("ios") || id.includes("iphone")) return "iOS";
  }
  return "Unknown";
}

function triggerFromContext(ctx) {
  if (!ctx) return "Policy Evaluation";
  // Match the image examples: "Location Anomaly", "Device Change"
  if (ctx.location_risk > 0.7) return "Location Anomaly";
  if (ctx.device_risk > 0.7) return "Device Change";
  if (ctx.behavior_risk > 0.7) return "Behavior Anomaly";
  if (ctx.network_risk > 0.7) return "Network Risk";
  if (ctx.past_incidents > 2) return "Past Incidents";
  return "Routine Check";
}

let donutChart = null;

function ensureDonut() {
  const ctx = $("donutChart").getContext("2d");
  if (donutChart) return donutChart;

  donutChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["Location", "Device", "Time", "Behavior"],
      datasets: [{
        data: [25, 25, 25, 25],
        backgroundColor: ["#5b86e5", "#36d1dc", "#f39c12", "#e74c3c"],
        borderWidth: 0,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "70%",
      plugins: {
        legend: { display: false },
        tooltip: { enabled: true },
      },
    },
  });
  return donutChart;
}

function setHealth(ok) {
  const pill = $("healthPill");
  const dot = document.createElement("span");
  dot.className = `pill-dot ${ok ? "ok" : "bad"}`;
  pill.innerHTML = "";
  pill.appendChild(dot);
  pill.appendChild(document.createTextNode(ok ? "API Healthy" : "API Down"));
}

const API_KEY = "zt-demo-key";

async function fetchJSON(url, opts) {
  const o = opts || {};
  const baseHeaders = { "X-API-Key": API_KEY };
  o.headers = Object.assign({}, baseHeaders, o.headers || {});

  const res = await fetch(url, o);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return await res.json();
}

async function loadHealth() {
  try {
    await fetchJSON("/health");
    setHealth(true);
  } catch {
    setHealth(false);
  }
}

function renderSessions(items) {
  const body = $("sessionsBody");
  body.innerHTML = "";

  for (const it of items.slice(0, 10)) {
    const t = it.trust_score ?? 0;
    const lvl = riskLevelFromTrust(t);
    const act = actionFromDecision(it.decision);
    const loc = it.context ? locationLabelFromContext(it.context) : "Unknown";
    const devType = it.context ? deviceTypeFromContext(it.context) : it.device_id;

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${it.user_id}</td>
      <td>${loc}</td>
      <td>${devType}</td>
      <td><strong>${trustPct(t)}</strong></td>
      <td><span class="badge ${lvl.cls}">${lvl.label}</span></td>
      <td><span class="badge ${act.cls}">${act.label}</span></td>
    `;
    body.appendChild(tr);
  }
}

function renderAlerts(items) {
  const body = $("alertsBody");
  body.innerHTML = "";
  for (const it of items.slice(0, 8)) {
    const act = actionFromDecision(it.decision);
    const t = it.trust_score ?? 0;
    // AI Confidence is based on how confident the model is (inverse of risk)
    const conf = `${clamp(Math.round((1 - Math.max(0, Math.min(1, t))) * 100), 0, 100)}%`;
    const timeStr = it.timestamp || "";
    let time = "";
    if (timeStr) {
      const d = new Date(timeStr);
      const hours = d.getUTCHours().toString().padStart(2, "0");
      const mins = d.getUTCMinutes().toString().padStart(2, "0");
      const ampm = hours >= 12 ? "PM" : "AM";
      const h12 = hours > 12 ? hours - 12 : (hours === 0 ? 12 : hours);
      time = `${h12}:${mins} ${ampm}`;
    } else {
      time = "-";
    }
    const trig = triggerFromContext(it.context);
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${time}</td>
      <td>${it.user_id}</td>
      <td>${trig}</td>
      <td><span class="badge ${act.cls}">${act.label}</span></td>
      <td>${conf}</td>
    `;
    body.appendChild(tr);
  }
}

function renderMetrics(items) {
  // metrics cards are now fetched from /metrics (real-time window)
}

function niceLabel(k) {
  const map = {
    user_risk: "User Risk",
    device_risk: "Device Risk",
    location_risk: "Location Risk",
    network_risk: "Network Risk",
    behavior_risk: "Behavior Anomaly",
    time_of_day_norm: "Login Time Risk",
    past_incidents_norm: "Past Incidents",
    sensitive_resource: "Sensitive Resource",
  };
  return map[k] || k;
}

function formatTimeOfDay(hour) {
  if (hour === undefined || hour === null) return "20%";
  const risk = hour < 7 || hour > 20 ? 0.2 : 0.05;
  return `${Math.round(risk * 100)}%`;
}

function renderBreakdown(latest) {
  const list = $("breakdownList");
  list.innerHTML = "";

  if (!latest || !latest.contributions) {
    $("trustGauge").textContent = "0";
    const chart = ensureDonut();
    chart.data.datasets[0].data = [25, 25, 25, 25];
    chart.update();
    return;
  }

  const trust = latest.trust_score ?? 0;
  $("trustGauge").textContent = String(trustPct(trust));

  // Show the exact items from the image: Login Time Risk, Location Risk, Device Risk, Behavior Anomaly, Final Trust Score
  const displayOrder = ["time_of_day_norm", "location_risk", "device_risk", "behavior_risk"];
  const contribs = displayOrder.map(k => {
    const v = latest.contributions[k] || 0;
    return [k, Math.max(0, Number(v) || 0)];
  });
  
  // Calculate percentages relative to total
  const sum = contribs.reduce((s, [, v]) => s + v, 0) || 1;
  const colorMap = {
    time_of_day_norm: "bar--orange",
    location_risk: "bar--green",
    device_risk: "bar--blue",
    behavior_risk: "bar--orange",
  };
  
  for (const [k, v] of contribs) {
    const pct = Math.round((v / sum) * 100);
    const colorClass = colorMap[k] || "";
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `
      <div class="row__label">${niceLabel(k)}</div>
      <div class="bar"><span class="${colorClass}" style="width:${pct}%"></span></div>
      <div class="row__value">${pct}%</div>
    `;
    list.appendChild(row);
  }
  
  // Add Final Trust Score row
  const trustRow = document.createElement("div");
  trustRow.className = "row";
  trustRow.style.fontWeight = "800";
  trustRow.style.marginTop = "8px";
  trustRow.style.paddingTop = "12px";
  trustRow.style.borderTop = "2px solid #e0e7f0";
  trustRow.innerHTML = `
    <div class="row__label">Final Trust Score</div>
    <div class="bar"><span class="bar--green" style="width:${trustPct(trust)}%"></span></div>
    <div class="row__value" style="font-weight: 800; color: #1b2430;">${trustPct(trust)}</div>
  `;
  list.appendChild(trustRow);

  // Donut: focus on 4 main items like the mockup.
  const want = ["time_of_day_norm", "location_risk", "device_risk", "behavior_risk"];
  const values = want.map((k) => {
    const found = latest.contributions[k];
    return Math.max(0, Number(found) || 0);
  });
  const s2 = values.reduce((s, x) => s + x, 0) || 1;
  const donutVals = values.map(v => Math.round((v / s2) * 100));

  const chart = ensureDonut();
  chart.data.labels = ["Login Time Risk", "Location Risk", "Device Risk", "Behavior Anomaly"];
  chart.data.datasets[0].data = donutVals;
  chart.data.datasets[0].backgroundColor = ["#f39c12", "#2ecc71", "#5b86e5", "#e74c3c"];
  chart.update();
}

async function loadDecisions() {
  const data = await fetchJSON("/decisions?limit=200");
  const items = data.items || [];

  renderSessions(items);
  renderAlerts(items);
  renderBreakdown(items[0]);
}

async function loadMetrics() {
  const m = await fetchJSON("/metrics?window_seconds=300");
  $("activeSessions").textContent = String(m.active_sessions ?? 0);
  $("highRiskUsers").textContent = String(m.high_risk_users ?? 0);
  $("avgTrust").textContent = String(m.average_trust_score ?? 0);
  $("blockedAttempts").textContent = String(m.blocked_attempts ?? 0);
}

function sliderKeys() {
  return [
    "location_risk",
    "device_risk",
    "time_of_day_norm",
    "behavior_risk",
  ];
}

function readSliders() {
  const out = {};
  for (const k of sliderKeys()) {
    const v = Number($(`s_${k}`).value || 0);
    out[k] = clamp(v / 100, 0, 1);
  }
  return out;
}

function syncSliderLabels() {
  for (const k of sliderKeys()) {
    const v = Number($(`s_${k}`).value || 0);
    $(`w_${k}`).textContent = `${v}%`;
  }
}

let lastWeights = null;

async function loadWeights() {
  const data = await fetchJSON("/config/weights");
  lastWeights = data.weights || {};
  for (const k of sliderKeys()) {
    const w = lastWeights[k];
    const pct = Math.round(clamp(Number(w) || 0, 0, 1) * 100);
    $(`s_${k}`).value = String(pct);
  }
  syncSliderLabels();
}

async function applyWeights() {
  const msg = $("weightsMsg");
  msg.textContent = "Applying…";
  try {
    const weights = readSliders();
    const data = await fetchJSON("/config/weights", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ weights }),
    });
    lastWeights = data.weights || {};
    msg.textContent = "Saved.";
    setTimeout(() => (msg.textContent = ""), 1200);
  } catch (e) {
    msg.textContent = `Failed: ${e.message}`;
  }
}

function resetWeights() {
  if (!lastWeights) return;
  for (const k of sliderKeys()) {
    const w = lastWeights[k];
    const pct = Math.round(clamp(Number(w) || 0, 0, 1) * 100);
    $(`s_${k}`).value = String(pct);
  }
  syncSliderLabels();
}

function wireSliders() {
  for (const k of sliderKeys()) {
    $(`s_${k}`).addEventListener("input", syncSliderLabels);
  }
  $("applyWeights").addEventListener("click", applyWeights);
  $("resetWeights").addEventListener("click", resetWeights);
  syncSliderLabels();
}

async function tick() {
  await loadHealth();
  await loadMetrics();
  await loadDecisions();
}

async function init() {
  initTheme();
  wireSliders();
  await loadWeights();
  await tick();
  setInterval(tick, 3000);
}

init().catch(() => {
  // If something fails early, still show health as down.
  setHealth(false);
});

