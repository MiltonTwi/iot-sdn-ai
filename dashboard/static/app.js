const $ = (s) => document.querySelector(s);
const fmt = (n) => Number(n || 0).toLocaleString("es-CO", { maximumFractionDigits: 1 });
const bytes = (b) => {
  if (b > 1e9) return (b / 1e9).toFixed(2) + " Gb/s";
  if (b > 1e6) return (b / 1e6).toFixed(2) + " Mb/s";
  if (b > 1e3) return (b / 1e3).toFixed(2) + " Kb/s";
  return fmt(b) + " b/s";
};

let zonesData = [];
let devicesData = [];
let attackLabelsActive = new Set();

async function loadStatic() {
  const [zones, devs, models] = await Promise.all([
    fetch("/api/zones").then(r => r.json()),
    fetch("/api/devices").then(r => r.json()),
    fetch("/api/models/metrics").then(r => r.json()),
  ]);
  zonesData = zones;
  devicesData = devs;

  $("#zones-count").textContent = zones.filter(z => z.id !== 0).length;
  $("#devs-count").textContent = devs.filter(d => d.role === undefined).length;

  renderZones({});
  renderDevices("");
  renderModels(models);
  loadAttacks();
}

function renderZones(byZone) {
  const wrap = $("#zones");
  wrap.innerHTML = "";
  for (const z of zonesData) {
    const live = byZone[z.name] || { pps: 0, bps: 0, device_count: z.device_count };
    const attacked = z.name === "infra" && attackLabelsActive.size > 0;
    const div = document.createElement("div");
    div.className = "zone" + (attacked ? " attacked" : "");
    const pct = Math.min(100, (live.pps / 200) * 100);
    div.innerHTML = `
      <div class="zname">${z.name} <small style="color:var(--muted)">#${z.id}</small></div>
      <div class="meta">${z.subnet} · ${live.device_count} dev · ${fmt(live.pps)} pps · ${bytes(live.bps)}</div>
      <div class="bar"><span style="width:${pct}%"></span></div>
    `;
    wrap.appendChild(div);
  }
}

function renderDevices(filter) {
  const tbody = $("#devices tbody");
  tbody.innerHTML = "";
  const f = filter.toLowerCase();
  const filtered = devicesData
    .filter(d => !d.role)
    .filter(d => !f || (d.name + " " + (d.zone || "") + " " + (d.proto || "")).toLowerCase().includes(f))
    .slice(0, 200);
  for (const d of filtered) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${d.name}</td><td>${d.zone}</td><td>${d.ip}</td>
      <td>${d.type || ""}</td><td>${d.proto || ""}</td><td>${d.rate_pps || 0}</td>
    `;
    tbody.appendChild(tr);
  }
}

function renderModels(metrics) {
  const tbody = $("#models tbody");
  tbody.innerHTML = "";
  if (!metrics || Object.keys(metrics).length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="color:var(--muted)">Sin modelos entrenados — corre <code>train_all.py</code></td></tr>`;
    return;
  }
  for (const [name, m] of Object.entries(metrics)) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${name}</td>
      <td>${(m.accuracy ?? 0).toFixed(4)}</td>
      <td>${(m.precision_macro ?? 0).toFixed(4)}</td>
      <td>${(m.recall_macro ?? 0).toFixed(4)}</td>
      <td>${(m.f1_macro ?? 0).toFixed(4)}</td>
      <td>${(m.train_s ?? 0).toFixed(1)}</td>
    `;
    tbody.appendChild(tr);
  }
}

async function loadAttacks() {
  const list = await fetch("/api/attacks/recent?limit=20").then(r => r.json());
  const tbody = $("#attacks tbody");
  tbody.innerHTML = "";
  attackLabelsActive = new Set();
  const now = Date.now() / 1000;
  for (const a of list) {
    const dur = (a.finished_at - a.started_at).toFixed(1);
    const start = new Date(a.started_at * 1000).toLocaleTimeString();
    if (a.finished_at > now - 5) attackLabelsActive.add(a.label);
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${a.label}</td><td>${a.family}</td><td>${start}</td><td>${dur}s</td>`;
    tbody.appendChild(tr);
  }
}

function connectWS() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const url = `${proto}://${location.host}/ws/feed`;
  $("#ws-url").textContent = url;
  const ws = new WebSocket(url);
  ws.onopen = () => $("#status").className = "dot online";
  ws.onclose = () => {
    $("#status").className = "dot offline";
    setTimeout(connectWS, 2000);
  };
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === "tick") {
      const p = msg.payload;
      $("#pps").textContent = fmt(p.pps_total);
      $("#bps").textContent = bytes(p.bps_total);
      $("#atk-active").textContent = (p.active_attacks || []).length;
      $("#ts").textContent = new Date(p.ts * 1000).toLocaleTimeString();
      renderZones(p.by_zone || {});
    }
  };
}

$("#dev-filter").addEventListener("input", (e) => renderDevices(e.target.value));

loadStatic();
connectWS();
setInterval(loadAttacks, 5000);
