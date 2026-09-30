# PASO 10 — Orquestación

**Fecha:** 2026-05-04
**Archivos:**
- `docker-compose.override.yaml` — extiende compose del base con dashboard + monturas IoT.
- `Makefile.iot` — 14 targets (`iot-up`, `iot-attack`, `iot-pipeline`, `iot-train`, `iot-tunnel`, …).
- `pyproject.iot.toml` — deps `[ml]`, `[dashboard]`, `[all]`.
- `scripts/env_check.ps1` — valida Docker, Python, WSL, puertos.
- `scripts/start_all.ps1` — secuencia end-to-end de 7 pasos.

---

## Comando único (end-to-end)

```powershell
cd C:\Users\mquui\iot-sdn-ai
.\scripts\start_all.ps1
```

Hace:
1. `env_check.ps1` (Docker/Python/WSL/puertos).
2. `generate_topology.py` (zones.yaml → network_config.iot.yaml).
3. `make iot-up` (controller, mininet, monitor, dashboard).
4. `make iot-topo` (topología 67 hosts, simuladores en background).
5. `make iot-attack-all` (14 escenarios secuenciales, ~25 min).
6. `make iot-pipeline RUN=...` (pcap → dataset.csv).
7. `make iot-train` + `iot-compare` (5 modelos + tabla).

Total: ~35 min en máquina típica. Saltable con `-SkipAttacks` o `-SkipTrain`.

---

## Targets del Makefile

| Target | Qué hace |
|---|---|
| `iot-gen` | YAML topología desde zones.yaml |
| `iot-up` | Levanta stack completo (controller+mininet+monitor+dash) |
| `iot-down` | Detiene stack |
| `iot-topo` | Inicia topología en Mininet con auto-traffic |
| `iot-attack SCN=<id> [DUR=60]` | Lanza un escenario |
| `iot-attack-all` | Los 14 escenarios secuenciales |
| `iot-capture RUN=<id>` | Captura PCAP en spine |
| `iot-pipeline RUN=<id>` | PCAP → flows → labeled → dataset |
| `iot-train RUN=<id>` | 5 modelos sobre dataset.csv |
| `iot-compare` | Tabla métricas |
| `iot-dash` | Dashboard standalone (sin Mininet) |
| `iot-tunnel MODE=lan\|cloudflared\|ngrok` | Expone al celular |
| `iot-clean` | Limpia datos generados |

---

## docker-compose.override.yaml — qué añade

| Servicio | Cambio |
|---|---|
| `mininet` | monta `./iot:/root/iot` y `./data:/root/data` |
| `dashboard` (nuevo) | FastAPI 8000, monta `iot/`, `ml_extra/artifacts/`, `/tmp` |
| `prometheus` | añade `alerts_iot.yaml` |
| `grafana` | añade `iot-overview.json` provisioned |

Se aplica con `-f SdnShare/docker-compose.yaml -f docker-compose.override.yaml` (ya en `COMPOSE` del Makefile).

---

## Tradeoffs

- **Makefile en Windows:** requiere `make` (instalable con `winget install GnuWin32.Make`) o usar WSL. Los scripts `.ps1` cubren las secuencias críticas sin make.
- **`iot-attack-all`** es secuencial. Paralelizarlos saturaría Mininet y produciría dataset confuso (varias etiquetas superpuestas en mismo flow). Secuencial = ~25 min, paralelo = ~5 min pero ruido grande. Mantenido secuencial.

---

## Próximo paso

`PASO-11-reproducibilidad.md` — README final, diagrama, lista de verificación.
