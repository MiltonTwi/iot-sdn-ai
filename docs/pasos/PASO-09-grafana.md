# PASO 09 — Integración Grafana + Prometheus alerts

**Fecha:** 2026-05-04
**Archivos:**
- `dashboard/grafana/iot-overview.json` — dashboard provisioned (8 paneles).
- `dashboard/grafana/provisioning/dashboards.yaml` — provider config.
- `dashboard/prometheus/alerts_iot.yaml` — 4 reglas de alerta.

---

## Decisión

El dashboard FastAPI (PASO-08) cubre **vista de negocio** (zonas, dispositivos, ataques, modelos). Grafana cubre **vista de operador SDN** (puertos, flujos, errores, dpids) — eso ya lo provee el monitor base de `SdnShare/infra/monitoring/monitor_prometheus.py` que expone métricas `ryu_monitor_*` automáticamente.

El overlay aporta:
- **Dashboard JSON provisioned** (no toca Grafana manualmente).
- **Alertas Prometheus IoT-aware** (spike, amplificación, errores, switches caídos).

---

## Paneles del dashboard `iot-overview`

| # | Panel | Métrica |
|---|---|---|
| 1 | Stat | `sum(rate(ryu_monitor_port_rx_packets[1m]))` — pps total |
| 2 | Stat | `sum(rate(ryu_monitor_port_rx_bytes[1m]))` — bytes/s |
| 3 | Stat | `sum(ryu_monitor_flow_packet_count)` — flujos |
| 4 | Stat | switches conectados |
| 5 | Time-series | RX bytes/s por dpid (leaf) |
| 6 | Time-series | top-10 puertos por pps |
| 7 | Time-series | RX/TX errors + drops |
| 8 | Time-series | delta de flujos (5m) |

---

## Reglas de alerta

| Alerta | Condición | Familia detectada |
|---|---|---|
| `PortRxPacketsSpike` | rate > 5000 pps por 30s | flood (SYN/UDP/ICMP/HTTP) |
| `ByteAmplification` | TX/RX ratio > 50x por 1m | DNS/CoAP/SSDP amplification |
| `HighRxErrors` | errores > 10/s por 1m | tráfico malformado, saturación |
| `NewSwitchDisappear` | switches < 10 por 1m | caída de leaf, error topología |

Las alertas dejan eventos en Prometheus → Grafana las muestra en el panel de alertas. Para enviar a Slack/email, añadir `alertmanager.yaml` (out of scope).

---

## Cómo se cargan

`docker-compose.override.yaml` (PASO-10) monta los archivos en sus rutas correctas:

```yaml
grafana:
  volumes:
    - ./dashboard/grafana/iot-overview.json:/etc/grafana/dashboards/iot/iot-overview.json
    - ./dashboard/grafana/provisioning:/etc/grafana/provisioning/dashboards-iot
prometheus:
  volumes:
    - ./dashboard/prometheus/alerts_iot.yaml:/etc/prometheus/alerts_iot.yaml
  command:
    - '--config.file=/etc/prometheus/prometheus.yml'
```

Y el `prometheus.yaml` base se modifica para incluir `rule_files: [alerts_iot.yaml]` (vía override en PASO-10).

---

## Acceso

Después de `make iot-up`:

- Grafana: `http://localhost:3000` (admin/admin) → carpeta **IoT-SDN-AI** → dashboard *IoT-SDN-AI Overview*.
- Prometheus: `http://localhost:9090` → tab Alerts.

Desde celular vía LAN: `http://<IP_LAN>:3000` (abrir firewall en 3000 igual que en 8000).

---

## Próximo paso

`PASO-10-orquestacion.md` — Makefile.iot + docker-compose.override.yaml.
