# PASO 01 — Arquitectura del overlay IoT

**Fecha:** 2026-05-04
**Objetivo:** Diseñar la estructura del proyecto sin modificar el repo base `SdnShare`.

---

## Decisión clave

El repo `SdnShare/` es la base inmutable: provee Mininet, Ryu, monitoreo (Prometheus/InfluxDB/Grafana/Graphite) y topologías genéricas (data-center spine-leaf). **No se modifica.**

Todo el trabajo IoT vive en un **overlay paralelo** en `iot-sdn-ai/` que:

- consume archivos de `SdnShare/infra/configs/` y `SdnShare/infra/topology/`,
- aporta sus propios scripts, simuladores, ataques, ML extra, dashboard y documentación,
- se orquesta con un `Makefile.iot` y `docker-compose.override.yaml`.

Razón: poder actualizar `SdnShare/` desde upstream sin perder trabajo, y dejar el overlay reutilizable.

---

## Árbol de carpetas final

```
iot-sdn-ai/
├── SdnShare/                          # base (no modificar)
├── iot/
│   ├── zones.yaml                     # catálogo: 7 zonas, 60+ dispositivos
│   ├── topology/
│   │   ├── generate_topology.py       # zones.yaml → network_config.iot.yaml
│   │   ├── network_config.iot.yaml    # generado, consumido por Mininet
│   │   └── mn_iot_topo.py             # topología Mininet IoT (extiende spineleaf)
│   ├── devices/
│   │   ├── base_device.py             # clase base con telemetría MQTT/CoAP/HTTP
│   │   ├── camera.py                  # stream UDP tipo RTSP
│   │   ├── sensor_mqtt.py             # publish periódico
│   │   ├── plc_modbus.py              # TCP simil-Modbus
│   │   ├── wearable_http.py           # POST de telemetría
│   │   ├── coap_device.py             # CoAP cliente
│   │   └── runner.py                  # arranca N procesos según zones.yaml
│   ├── attacks/
│   │   ├── catalog.yaml               # 12+ escenarios
│   │   ├── runner.py                  # ejecuta un ataque por nombre
│   │   └── scenarios/
│   │       ├── syn_flood.py
│   │       ├── udp_flood.py
│   │       ├── icmp_flood.py
│   │       ├── http_flood.py
│   │       ├── slowloris.py
│   │       ├── port_scan.py
│   │       ├── arp_spoof.py
│   │       ├── dns_amplification.py
│   │       ├── coap_amplification.py
│   │       ├── ssdp_amplification.py
│   │       ├── mqtt_subscribe_flood.py
│   │       ├── mqtt_malformed.py
│   │       ├── credential_bruteforce.py
│   │       └── mirai_coordinated.py
│   └── pipeline/
│       ├── flow_extractor.py          # PCAP → flow records (CICFlowMeter-like)
│       ├── feature_engineering.py     # IAT, entropy, MQTT/CoAP campos
│       └── label_dataset.py           # cruza con catalog.yaml para etiquetar
├── ml_extra/
│   ├── train_all.py                   # entrena 5 modelos en paralelo
│   ├── compare.py                     # tabla comparativa precision/recall/F1
│   ├── models/
│   │   ├── rf.py
│   │   ├── xgb.py
│   │   ├── mlp.py
│   │   ├── isoforest.py
│   │   └── autoencoder.py
│   └── artifacts/                     # modelos entrenados (.joblib, .pt)
├── dashboard/
│   ├── app.py                         # FastAPI + WebSocket
│   ├── metrics_collector.py           # consume Prometheus + estado en vivo
│   ├── detector_service.py            # carga modelo, infiere sobre flujos
│   ├── static/
│   │   ├── index.html                 # SPA mobile-responsive
│   │   ├── app.js
│   │   └── styles.css
│   └── Dockerfile
├── docs/
│   ├── PASO-01-arquitectura.md       # este archivo
│   ├── PASO-02-zonas-dispositivos.md
│   ├── PASO-03-topologia.md
│   ├── PASO-04-simuladores.md
│   ├── PASO-05-ataques.md
│   ├── PASO-06-pipeline.md
│   ├── PASO-07-modelos-ml.md
│   ├── PASO-08-dashboard.md
│   ├── PASO-09-grafana.md
│   ├── PASO-10-orquestacion.md
│   ├── PASO-11-reproducibilidad.md
│   └── DIAGRAMA-final.md
├── scripts/
│   ├── env_check.ps1                  # valida Docker/WSL2
│   ├── start_all.ps1                  # arranca todo end-to-end
│   └── tunnel_phone.ps1               # cloudflared tunnel para celular
├── Makefile.iot                       # targets iot-up/iot-attack/iot-train/iot-dash
├── docker-compose.override.yaml       # añade dashboard al stack
├── docs/guias/laboratorio.md                      # entrypoint del overlay
└── pyproject.iot.toml                 # deps extra (xgboost, torch, fastapi…)
```

---

## Diagrama de flujo

```
┌─────────────────────┐
│  iot/zones.yaml     │  declarativo
└──────────┬──────────┘
           │ generate_topology.py
           ▼
┌─────────────────────┐    ┌──────────────────┐
│ network_config.     │───▶│ Mininet + Ryu    │
│ iot.yaml            │    │ (SdnShare base)  │
└─────────────────────┘    └────────┬─────────┘
                                    │
           ┌────────────────────────┼────────────────────────┐
           ▼                        ▼                        ▼
   iot/devices/runner.py    iot/attacks/runner.py    monitor_*.py (base)
   60+ procesos por zona   12+ escenarios            métricas → Prom/Influx/Graphite
           │                        │
           └──────────┬─────────────┘
                      ▼
            tshark/pcap → iot/pipeline
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
   flow_extractor  feature_eng   label_dataset
                      │
                      ▼
                ml_extra/train_all.py  → 5 modelos
                      │
                      ▼
              dashboard/detector_service.py
                      │
                      ▼
            FastAPI + WebSocket (0.0.0.0:8000)
                      │
                      ▼
              celular en LAN o ngrok
```

---

## Convenciones

- **Subred IoT:** `10.10.0.0/16` (no choca con 10.1.1.0/24 del base).
- **Subred por zona:** `10.10.{ZONA}.0/24` con ZONA ∈ 1..7.
- **MAC:** `02:1o:t0:{ZONA:02x}:{DEV:02x}:00`.
- **Etiquetas dataset:** `BENIGN | <attack_name>` (ej. `MIRAI_SYN_FLOOD`).
- **Run ID:** `YYYYmmdd-HHMMSS_{escenario}` (heredado de `scripts/generate_run_id.py`).

---

## Acceso desde el celular

El dashboard se enlaza a `0.0.0.0:8000`. Tres formas de acceder desde el celular:

1. **LAN (más simple):** PC y celular en el mismo Wi-Fi → `http://<IP_LAN_PC>:8000`. La IP se obtiene con `ipconfig` (Windows) buscando "IPv4". Abrir Firewall: `New-NetFirewallRule -DisplayName "IoT Dash" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow`.
2. **Cloudflare Tunnel (sin abrir router):** `cloudflared tunnel --url http://localhost:8000`. Dashboard queda con URL `https://*.trycloudflare.com`.
3. **ngrok:** `ngrok http 8000`.

Detalle paso a paso: `docs/pasos/PASO-08-dashboard.md` y `scripts/tunnel_phone.ps1`.

---

## Próximo paso

`PASO-02-zonas-dispositivos.md` — define el catálogo IoT.
