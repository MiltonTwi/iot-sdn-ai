#!/usr/bin/env python3
"""
Dashboard IoT — FastAPI + WebSocket.

Bind 0.0.0.0:8000 para acceso desde celular en LAN.

Endpoints:
  GET  /                     → SPA estática (static/index.html)
  GET  /api/zones            → resumen por zona desde zones.yaml
  GET  /api/devices          → lista plana de dispositivos
  GET  /api/metrics/live     → snapshot actual (counters)
  GET  /api/attacks/recent   → últimos manifests de /tmp/attack_*.json
  GET  /api/models/metrics   → métricas de los modelos entrenados
  WS   /ws/feed              → stream de eventos {ts, type, payload}

Modo "demo" (sin Mininet): genera tráfico sintético si no encuentra fuente real.
"""

from __future__ import annotations

import asyncio
import glob
import json
import os
import random
import time
from pathlib import Path

import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
ZONES_YAML = ROOT / "iot" / "zones.yaml"
ATTACK_GLOB = "/tmp/attack_*.json"
ML_METRICS = ROOT / "ml_extra" / "artifacts" / "metrics.json"
HOSTS_JSON = Path("/tmp/iot_hosts.json")
STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="IoT-SDN-AI Dashboard")

if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


# ─── helpers ─────────────────────────────────────────────────────

def _zones_doc() -> dict:
    with ZONES_YAML.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _devices_flat() -> list[dict]:
    doc = _zones_doc()
    out: list[dict] = []
    for h in doc["infrastructure"]["hosts"]:
        out.append({**h, "zone": "infra"})
    for z in doc["zones"]:
        for d in z["devices"]:
            out.append({**d, "zone": z["name"], "zone_id": z["id"]})
    return out


def _attacks_recent(limit: int = 20) -> list[dict]:
    files = sorted(glob.glob(ATTACK_GLOB), reverse=True)[:limit]
    out: list[dict] = []
    for f in files:
        try:
            out.append(json.loads(Path(f).read_text()))
        except Exception:
            continue
    return out


def _models_metrics() -> dict:
    if ML_METRICS.exists():
        return json.loads(ML_METRICS.read_text())
    return {}


# ─── REST ───────────────────────────────────────────────────────

@app.get("/")
def index():
    f = STATIC / "index.html"
    if f.exists():
        return FileResponse(str(f))
    return JSONResponse({"hint": "static/index.html no encontrado"})


@app.get("/api/zones")
def api_zones():
    doc = _zones_doc()
    out = [
        {
            "id": z["id"], "name": z["name"], "subnet": z["subnet"],
            "device_count": len(z["devices"]), "description": z["description"],
        }
        for z in doc["zones"]
    ]
    out.append({
        "id": 0, "name": "infra", "subnet": doc["infrastructure"]["subnet"],
        "device_count": len(doc["infrastructure"]["hosts"]),
        "description": "Servidores compartidos (MQTT/CoAP/HTTP/DNS/NTP/SSDP) + attacker",
    })
    return out


@app.get("/api/devices")
def api_devices():
    return _devices_flat()


@app.get("/api/attacks/recent")
def api_attacks(limit: int = 20):
    return _attacks_recent(limit)


@app.get("/api/models/metrics")
def api_models():
    return _models_metrics()


@app.get("/api/metrics/live")
def api_live():
    return _live_snapshot()


# ─── live state (in-memory, demo si no hay fuente) ──────────────

_state = {
    "started_at": time.time(),
    "pps_total": 0,
    "bps_total": 0,
    "active_attacks": [],
    "by_zone": {},
}


def _live_snapshot() -> dict:
    return {**_state, "ts": time.time()}


async def _tick() -> None:
    """Bucle de actualización del estado live.

    Si encuentra HOSTS_JSON (escrito por mn_iot_topo.py), basa pps en rate_pps
    declarado; si no, sintético para que el dashboard sea visible en demo.
    """
    while True:
        zones = _zones_doc()
        active = _attacks_recent(5)
        active = [a for a in active if a.get("finished_at", 0) >= time.time() - 5]

        by_zone: dict[str, dict] = {}
        total_pps = 0
        for z in zones["zones"]:
            zone_pps = sum(d["rate_pps"] for d in z["devices"])
            zone_bps = sum(d["rate_pps"] * d["payload"] * 8 for d in z["devices"])
            jitter = random.uniform(0.85, 1.15)
            by_zone[z["name"]] = {
                "id": z["id"],
                "pps": round(zone_pps * jitter, 1),
                "bps": int(zone_bps * jitter),
                "device_count": len(z["devices"]),
            }
            total_pps += zone_pps * jitter

        # ataques activos suman pps grande artificialmente
        for a in active:
            cfg = a.get("config", {})
            attack_rate = cfg.get("rate_pps", 0)
            zone_target = "infra"
            if zone_target in by_zone:
                by_zone[zone_target]["pps"] += attack_rate
            total_pps += attack_rate

        _state["pps_total"] = round(total_pps, 1)
        _state["bps_total"] = sum(z["bps"] for z in by_zone.values())
        _state["by_zone"] = by_zone
        _state["active_attacks"] = [
            {"label": a["label"], "started_at": a["started_at"], "scenario": a["scenario"]}
            for a in active
        ]
        await asyncio.sleep(1.0)


# ─── WebSocket ──────────────────────────────────────────────────

class Hub:
    def __init__(self):
        self.clients: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.clients:
            self.clients.remove(ws)

    async def broadcast(self, msg: dict):
        dead = []
        for c in self.clients:
            try:
                await c.send_json(msg)
            except Exception:
                dead.append(c)
        for d in dead:
            self.disconnect(d)


hub = Hub()


@app.websocket("/ws/feed")
async def feed(ws: WebSocket):
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()  # ignora pings cliente
    except WebSocketDisconnect:
        hub.disconnect(ws)


async def _broadcaster() -> None:
    while True:
        await hub.broadcast({"ts": time.time(), "type": "tick", "payload": _live_snapshot()})
        await asyncio.sleep(1.0)


@app.on_event("startup")
async def _startup():
    asyncio.create_task(_tick())
    asyncio.create_task(_broadcaster())


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("DASH_HOST", "0.0.0.0")
    port = int(os.getenv("DASH_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
