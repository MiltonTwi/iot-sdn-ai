# IoT-SDN-AI Lab

[English](laboratorio.en.md) · **Español**

Laboratorio para **detección de ataques IoT con AI sobre SDN**, construido como overlay del repo base [SdnShare](https://github.com/JosephRodriri/SdnShare).

- **67 hosts** (60 dispositivos IoT en 7 zonas + 6 servidores + 1 atacante)
- **14 escenarios de ataque** (DDoS, low-rate, recon, MITM, amplification, protocol-abuse, bruteforce, botnet)
- **5 modelos ML** (Random Forest, XGBoost, MLP, Isolation Forest, AutoEncoder)
- **Dashboard web FastAPI** (mobile-friendly + WebSocket) + Grafana provisioned
- **Documentación paso a paso** en `docs/pasos/PASO-XX-*.md`

---

## Quickstart

### Prerequisitos
- VM Ubuntu 22.04 (Multipass/Hyper-V) con Docker; ≥ 4 GB de RAM para la VM
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
   │ 6 serv+atac   15 dev                          5 dev          │
   └──────┬──────────────┬───────────────────────────────────────┘
          │              │
   simuladores       atacantes
   (60+ procesos)    (14 escenarios)
          │              │
          └──────┬───────┘
                 ▼
   tcpdump (puerto espejo s_iot_0)
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
| [02](../pasos/PASO-02-zonas-dispositivos.md) | 7 zonas, 60 dispositivos |
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

Ver la sección "Estructura del repositorio" del [`README.md`](../../README.md) principal.

---

## Resultados obtenidos

Cifras vigentes (detalle y protocolo en [`../resultados/RESULTADOS-FINAL.md`](../resultados/RESULTADOS-FINAL.md)):

| Métrica | Valor |
|---|---|
| Dataset | 505.768 flujos, 14 clases, 50 características |
| F1-macro Random Forest (CV agrupada, sin fuga) | 0,986 ± 0,014 |
| Detección ataque/benigno | F1 0,995 · AUC 0,999; externo CIC-IoT-2023 F1 0,940 |
| Lazo cerrado (ventana 2 s) | 39/39 ataques mitigados, 0 falsas alarmas, tiempo mediano 2,5 s |

---

## Tradeoffs documentados

- Mininet en Docker requiere privileged y un kernel Linux: corre en una VM Ubuntu (Multipass/Hyper-V); en WSL2 OVS se caía.
- ARP spoof opera en capa 2 (sin flujos IP): queda fuera del clasificador y lo cubre el anti-spoofing IP-MAC del controlador.
- AutoEncoder con sklearn MLPRegressor (no PyTorch) → 85% del rendimiento, cero deps extra. Pendiente: LSTM-AE en torch.
- `iot-attack-all` secuencial (~25 min) en lugar de paralelo (~5 min) → datos limpios sin etiquetas superpuestas.

---

## Licencia

Código propio bajo MIT (ver [`LICENSE`](../../LICENSE)). El laboratorio base [SdnShare](https://github.com/JosephRodriri/SdnShare) no declara licencia; se incluye con crédito a su autor.

Proyecto de trabajo de grado — Ingeniería de Sistemas, Universidad Cooperativa de Colombia (2026).
