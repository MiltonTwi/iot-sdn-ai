# IoT-SDN-AI Lab

Laboratorio para **detección de ataques IoT con AI sobre SDN**, construido como overlay del repo base [SdnShare](https://github.com/JosephRodriri/SdnShare).

- **70 hosts** (63 dispositivos IoT + 7 servidores) en 7 zonas
- **14 escenarios de ataque** (DDoS, low-rate, recon, MITM, amplification, protocol-abuse, bruteforce, botnet)
- **5 modelos ML** (Random Forest, XGBoost, MLP, Isolation Forest, AutoEncoder)
- **Dashboard web FastAPI** (mobile-friendly + WebSocket) + Grafana provisioned
- **Documentación paso a paso** en `docs/pasos/PASO-XX-*.md`

---

## Quickstart

### Prerequisitos
- Windows 11 con Docker Desktop + WSL2
- Python 3.10+
- 8 GB RAM libres recomendados

### 1) Validar entorno
```powershell
cd C:\Users\mquui\iot-sdn-ai
.\scripts\env_check.ps1
```

### 2) Run end-to-end (35 min)
```powershell
.\scripts\start_all.ps1
```

### 3) Acceder a dashboards
- IoT dashboard: <http://localhost:8000>
- Grafana: <http://localhost:3000> (admin/admin)
- FlowManager: <http://localhost:8080>
- Prometheus: <http://localhost:9090>

### 4) Acceder desde celular
```powershell
.\scripts\tunnel_phone.ps1 lan          # mismo Wi-Fi
.\scripts\tunnel_phone.ps1 cloudflared  # URL pública (datos móviles ok)
```

---

## Arquitectura

```
                         ┌──────────────────┐
                         │  iot/zones.yaml  │
                         │  (catálogo)      │
                         └────────┬─────────┘
                                  ▼
                ┌──────────────────────────────────┐
                │ generate_topology.py             │
                │ network_config.iot.yaml          │
                └────────┬─────────────────────────┘
                         ▼
   ┌─────────────────────────────────────────────────────────────┐
   │  Mininet (Docker, privileged) + Ryu controller              │
   │  ┌─────────┐ ┌─────────┐                                    │
   │  │spine_1  │ │spine_2  │   (full mesh)                      │
   │  └────┬────┘ └────┬────┘                                    │
   │   ┌───┴────┐  ┌───┴────┐  ...                ┌──────────┐   │
   │   │s_iot_0 │  │s_iot_1 │                     │s_iot_7   │   │
   │   │ infra  │  │ home   │                     │ retail   │   │
   │   └───┬────┘  └───┬────┘                     └────┬─────┘   │
   │   7 servers   15 dev                          5 dev          │
   └──────┬──────────────┬───────────────────────────────────────┘
          │              │
   simuladores       atacantes
   (60+ procesos)    (14 escenarios)
          │              │
          └──────┬───────┘
                 ▼
            tshark PCAP
                 │
                 ▼
       iot/pipeline/  (flow → label → features)
                 │
                 ▼
       data/processed/{run}/dataset.csv
                 │
                 ▼
       ml_extra/train_all.py  (5 modelos)
                 │
                 ▼
   ┌───────────────────────┐    ┌────────────────────┐
   │ FastAPI dashboard 8000│    │ Grafana 3000       │
   │ - mapa zonas          │    │ - vista operador   │
   │ - métricas live (WS)  │    │ - alertas IoT      │
   │ - tabla modelos       │    └────────────────────┘
   └───────────────────────┘
            │
            ▼
   celular (LAN o cloudflared)
```

---

## Documentación

| Paso | Tema |
|---|---|
| [01](../pasos/PASO-01-arquitectura.md) | Arquitectura overlay + estructura |
| [02](../pasos/PASO-02-zonas-dispositivos.md) | 7 zonas, 63 dispositivos |
| [03](../pasos/PASO-03-topologia.md) | Generador Mininet IoT |
| [04](../pasos/PASO-04-simuladores.md) | Simuladores stdlib pura |
| [05](../pasos/PASO-05-ataques.md) | 14 escenarios |
| [06](../pasos/PASO-06-pipeline.md) | PCAP → dataset etiquetado |
| [07](../pasos/PASO-07-modelos-ml.md) | 5 modelos ML |
| [08](../pasos/PASO-08-dashboard.md) | Dashboard + acceso celular |
| [09](../pasos/PASO-09-grafana.md) | Grafana + Prometheus alerts |
| [10](../pasos/PASO-10-orquestacion.md) | Makefile + compose override |
| [11](../pasos/PASO-11-reproducibilidad.md) | Reproducibilidad y checklist |
| [12](../pasos/PASO-12-importer.md) | Importador automático (GraphML / NetworkX / Mininet / Ryu API) |
| [13](../pasos/PASO-13-mitigacion.md) | Mitigación SDN (DROP + OF Meters) + Anti-Spoof IP-MAC + bridge detector |
| [14](../pasos/PASO-14-evaluacion.md) | Reporte PDF + bench latencia + demo push-button + tests + audit log |
| [15](../pasos/PASO-15-cross-eval.md) | Naive baseline + SHAP + cross-eval con CIC-IoT-2023 |

---

## Estructura

```
iot-sdn-ai/
├── SdnShare/                  # base (no modificar)
├── iot/
│   ├── zones.yaml             # 7 zonas, 63 dispositivos
│   ├── topology/
│   ├── devices/               # simuladores + servers stdlib
│   ├── attacks/               # 14 escenarios
│   └── pipeline/              # flow_extractor + label + features
├── ml_extra/
│   ├── models/                # rf, xgb, mlp, isoforest, autoencoder
│   └── train_all.py
├── dashboard/                 # FastAPI + static SPA + Grafana JSON + Prom alerts
├── docs/                      # PASO-XX-*.md
├── scripts/                   # env_check, start_all, tunnel_phone
├── docker-compose.override.yaml
├── Makefile.iot
├── pyproject.iot.toml
└── README.iot.md
```

---

## Resultados esperados

Tras `start_all.ps1` con duración por defecto:

| Métrica | Valor típico |
|---|---|
| Paquetes capturados | ~600,000 en 30 min |
| Flujos extraídos | 50,000 - 100,000 |
| Etiquetas únicas | 15 (BENIGN + 14 ataques) |
| Accuracy RF/XGB | 0.96 - 0.99 |
| Accuracy MLP | 0.92 - 0.96 |
| Accuracy IsoForest/AE (binario) | 0.88 - 0.94 |
| F1-macro mejor modelo | ~0.96 |

---

## Tradeoffs documentados

- Mininet en Docker requiere privileged + WSL2 → no corre en Windows nativo.
- ARP spoof depende de bridge en modo promiscuo → puede fallar; manifest queda con `return_code=1` y se omite del dataset.
- AutoEncoder con sklearn MLPRegressor (no PyTorch) → 85% del rendimiento, cero deps extra. Pendiente: LSTM-AE en torch.
- `iot-attack-all` secuencial (~25 min) en lugar de paralelo (~5 min) → datos limpios sin etiquetas superpuestas.

---

## Licencia

Overlay propio (este repo). Repo base SdnShare bajo MIT (Maen Artimy).

Proyecto académico — semillero de investigación, deadline 2026-05-17.
