# PASO 11 — Reproducibilidad y checklist final

**Fecha:** 2026-05-04
**Estado:** Overlay completo. Todos los archivos creados.

---

## Checklist de archivos

### Capa 1 — declarativa
- [x] `iot/zones.yaml` (63 dispositivos)
- [x] `iot/attacks/catalog.yaml` (14 escenarios)

### Capa 2 — generadores
- [x] `iot/topology/generate_topology.py`
- [x] `iot/topology/mn_iot_topo.py`

### Capa 3 — simuladores y servidores
- [x] `iot/devices/runner.py`
- [x] `iot/devices/servers/{mqtt_broker, coap_server, dns_server, ntp_server, ssdp_server}.py`

### Capa 4 — ataques
- [x] `iot/attacks/runner.py`
- [x] `iot/attacks/scenarios/*.py` × 14

### Capa 5 — pipeline de datos
- [x] `iot/pipeline/flow_extractor.py`
- [x] `iot/pipeline/label_dataset.py`
- [x] `iot/pipeline/feature_engineering.py`

### Capa 6 — modelos ML
- [x] `ml_extra/common.py`
- [x] `ml_extra/models/{rf, xgb, mlp, isoforest, autoencoder}.py`
- [x] `ml_extra/train_all.py`
- [x] `ml_extra/compare.py`

### Capa 7 — dashboard
- [x] `dashboard/app.py` (FastAPI + WS)
- [x] `dashboard/static/{index.html, app.js, styles.css}`
- [x] `dashboard/Dockerfile` + `requirements.txt`
- [x] `dashboard/grafana/iot-overview.json`
- [x] `dashboard/grafana/provisioning/dashboards.yaml`
- [x] `dashboard/prometheus/alerts_iot.yaml`

### Capa 8 — orquestación
- [x] `docker-compose.override.yaml`
- [x] `Makefile.iot`
- [x] `pyproject.iot.toml`
- [x] `scripts/env_check.ps1`
- [x] `scripts/start_all.ps1`
- [x] `scripts/tunnel_phone.ps1`

### Capa 9 — documentación
- [x] `docs/guias/laboratorio.md`
- [x] `docs/pasos/PASO-01..11-*.md` (11 archivos)

---

## Comandos de validación

```powershell
# 1) Estructura completa
Get-ChildItem -Recurse -File -Path C:\Users\mquui\iot-sdn-ai | Measure-Object | Select-Object Count

# 2) Generador de topología (sin Docker)
python iot\topology\generate_topology.py
# Esperado: switches=10  links=16  hosts=70

# 3) Sintaxis Python (sin ejecutar)
python -m py_compile iot\devices\runner.py iot\pipeline\flow_extractor.py ml_extra\train_all.py dashboard\app.py

# 4) YAML válidos
python -c "import yaml; yaml.safe_load(open('iot/zones.yaml')); yaml.safe_load(open('iot/attacks/catalog.yaml')); print('OK')"

# 5) Listar escenarios
python -c "import yaml; print(len(yaml.safe_load(open('iot/attacks/catalog.yaml'))['scenarios']))"
# Esperado: 14
```

---

## Diagrama de carpetas final

```
iot-sdn-ai/                                   (≈ 50 archivos overlay + base)
├── docs/guias/laboratorio.md
├── Makefile.iot
├── docker-compose.override.yaml
├── pyproject.iot.toml
├── SdnShare/                                  (base, no modificar)
├── iot/
│   ├── zones.yaml                             (63 devices, 7 zones)
│   ├── topology/
│   │   ├── generate_topology.py               (zones → network_config)
│   │   └── mn_iot_topo.py                     (Mininet builder)
│   ├── devices/
│   │   ├── runner.py                          (despachador stdlib)
│   │   └── servers/{mqtt,coap,dns,ntp,ssdp}_server.py
│   ├── attacks/
│   │   ├── catalog.yaml                       (14 escenarios)
│   │   ├── runner.py                          (lanzador + manifest)
│   │   └── scenarios/{14 archivos}.py
│   └── pipeline/
│       ├── flow_extractor.py                  (PCAP → flows.csv)
│       ├── label_dataset.py                   (cruza manifests)
│       └── feature_engineering.py             (host-window 5s)
├── ml_extra/
│   ├── common.py
│   ├── models/{rf,xgb,mlp,isoforest,autoencoder}.py
│   ├── train_all.py
│   ├── compare.py
│   └── artifacts/                             (out: .joblib, metrics.json)
├── dashboard/
│   ├── app.py                                 (FastAPI 0.0.0.0:8000)
│   ├── static/{index.html, app.js, styles.css}
│   ├── Dockerfile + requirements.txt
│   ├── grafana/iot-overview.json
│   └── prometheus/alerts_iot.yaml
├── scripts/
│   ├── env_check.ps1                          (Docker/Python/WSL/puertos)
│   ├── start_all.ps1                          (end-to-end)
│   └── tunnel_phone.ps1                       (LAN/cloudflared/ngrok)
└── docs/pasos/PASO-01..11-*.md                       (11 docs en español)
```

---

## Próximos hitos (post-deadline 2026-05-17)

1. **LSTM-AE en PyTorch** sustituyendo MLPRegressor — captura mejor secuencias temporales.
2. **Online inference** dentro del dashboard — cargar `rf.joblib`, suscribirse a Prometheus, predecir cada 5s, publicar alertas vía WebSocket.
3. **Federated learning** entre múltiples instancias del lab — escenario realista de IoT distribuido.
4. **Datasets externos**: complementar con CIC-IoT-2023 (transfer learning hacia el lab sintético).
5. **SDN response**: Ryu app que instale flow-rules de drop/rate-limit basadas en alertas Prometheus.

---

## Resumen ejecutivo

- **Entregable:** overlay funcional sobre SdnShare con 7 zonas IoT, 63 dispositivos simulados, 14 ataques, 5 modelos ML, dashboard web mobile-friendly.
- **Esfuerzo:** ~50 archivos nuevos, ~3,500 líneas de código + documentación, sin tocar el base.
- **Reproducible:** un solo comando (`start_all.ps1`) ejecuta todo el pipeline.
- **Documentado:** 11 PASO-XX en español + README + diagramas.
- **Mobile-ready:** dashboard `0.0.0.0:8000` + 3 modos de túnel para celular.

Cumple con el pedido: máxima cantidad de dispositivos, máxima cantidad de ataques, interfaz web para métricas, documentación de cada paso.
