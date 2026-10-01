# IoT-SDN-AI Lab

**English** · [Español](laboratorio.md)

Lab for **IoT attack detection with AI over SDN**, built as an overlay on the base repo [SdnShare](https://github.com/JosephRodriri/SdnShare).

- **67 hosts** (60 IoT devices in 7 zones + 6 servers + 1 attacker)
- **14 attack scenarios** (DDoS, low-rate, recon, MITM, amplification, protocol abuse, brute force, botnet)
- **5 ML models** (Random Forest, XGBoost, MLP, Isolation Forest, AutoEncoder)
- **FastAPI web dashboard** (mobile-friendly + WebSocket) + provisioned Grafana
- **Step-by-step documentation** in `docs/pasos/PASO-XX-*.md` (Spanish)

---

## Quickstart

### Prerequisites
- Ubuntu 22.04 VM (Multipass/Hyper-V) with Docker; ≥ 4 GB RAM for the VM
- Python 3.10+
- 8 GB free RAM recommended

### 1) Validate environment
```powershell
cd C:\Users\mquui\iot-sdn-ai
.\scripts\env_check.ps1
```

### 2) End-to-end run (35 min)
```powershell
.\scripts\start_all.ps1
```

### 3) Open dashboards
- IoT dashboard: <http://localhost:8000>
- Grafana: <http://localhost:3000> (admin/admin)
- FlowManager: <http://localhost:8080>
- Prometheus: <http://localhost:9090>

### 4) Access from a phone
```powershell
.\scripts\tunnel_phone.ps1 lan          # same Wi-Fi
.\scripts\tunnel_phone.ps1 cloudflared  # public URL (mobile data OK)
```

---

## Architecture

```
                         ┌──────────────────┐
                         │  iot/zones.yaml  │
                         │  (catalog)       │
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
   │ 6 srv+attacker 15 dev                         5 dev          │
   └──────┬──────────────┬───────────────────────────────────────┘
          │              │
     simulators       attackers
   (60+ processes)   (14 scenarios)
          │              │
          └──────┬───────┘
                 ▼
   tcpdump (s_iot_0 mirror port)
                 │
                 ▼
       iot/pipeline/  (flow → label → features)
                 │
                 ▼
       data/processed/{run}/dataset.csv
                 │
                 ▼
       ml_extra/train_all.py  (5 models)
                 │
                 ▼
   ┌───────────────────────┐    ┌────────────────────┐
   │ FastAPI dashboard 8000│    │ Grafana 3000       │
   │ - zone map            │    │ - operator view    │
   │ - live metrics (WS)   │    │ - IoT alerts       │
   │ - model table         │    └────────────────────┘
   └───────────────────────┘
            │
            ▼
   phone (LAN or cloudflared)
```

---

## Documentation (Spanish)

| Step | Topic |
|---|---|
| [01](../pasos/PASO-01-arquitectura.md) | Overlay architecture + layout |
| [02](../pasos/PASO-02-zonas-dispositivos.md) | 7 zones, 60 devices |
| [03](../pasos/PASO-03-topologia.md) | IoT Mininet generator |
| [04](../pasos/PASO-04-simuladores.md) | Pure-stdlib simulators |
| [05](../pasos/PASO-05-ataques.md) | 14 scenarios |
| [06](../pasos/PASO-06-pipeline.md) | PCAP → labeled dataset |
| [07](../pasos/PASO-07-modelos-ml.md) | 5 ML models |
| [08](../pasos/PASO-08-dashboard.md) | Dashboard + phone access |
| [09](../pasos/PASO-09-grafana.md) | Grafana + Prometheus alerts |
| [10](../pasos/PASO-10-orquestacion.md) | Makefile + compose override |
| [11](../pasos/PASO-11-reproducibilidad.md) | Reproducibility and checklist |
| [12](../pasos/PASO-12-importer.md) | Automatic importer (GraphML / NetworkX / Mininet / Ryu API) |
| [13](../pasos/PASO-13-mitigacion.md) | SDN mitigation (DROP + OF meters) + IP-MAC anti-spoof + bridge detector |
| [14](../pasos/PASO-14-evaluacion.md) | PDF report + latency bench + push-button demo + tests + audit log |
| [15](../pasos/PASO-15-cross-eval.md) | Naive baseline + SHAP + cross-eval with CIC-IoT-2023 |

---

## Layout

See the "Repository layout" section of the main [`README.en.md`](../../README.en.md).

---

## Results

Current figures (details and protocol in [`../resultados/RESULTADOS-FINAL.en.md`](../resultados/RESULTADOS-FINAL.en.md)):

| Metric | Value |
|---|---|
| Dataset | 505,768 flows, 14 classes, 50 features |
| Random Forest F1-macro (grouped CV, leak-free) | 0.986 ± 0.014 |
| Attack/benign detection | F1 0.995 · AUC 0.999; external CIC-IoT-2023 F1 0.940 |
| Closed loop (2 s window) | 39/39 attacks mitigated, 0 false alarms, median time 2.5 s |

---

## Documented tradeoffs

- Mininet in Docker needs privileged mode and a Linux kernel: it runs in an Ubuntu VM (Multipass/Hyper-V); under WSL2, OVS crashed.
- ARP spoofing operates at layer 2 (no IP flows): it is outside the flow classifier and is covered by the controller's IP-MAC anti-spoofing.
- AutoEncoder with sklearn MLPRegressor (not PyTorch) → 85 % of the performance, zero extra deps. Pending: LSTM-AE in torch.
- Sequential `iot-attack-all` (~25 min) instead of parallel (~5 min) → clean data without overlapping labels.

---

## License

Original code under MIT (see [`LICENSE`](../../LICENSE)). The base lab [SdnShare](https://github.com/JosephRodriri/SdnShare) declares no license; it is included with credit to its author.

Undergraduate thesis project — Systems Engineering, Universidad Cooperativa de Colombia (2026).
