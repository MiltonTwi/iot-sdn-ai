# PASO 08 — Dashboard web (FastAPI + WebSocket)

**Fecha:** 2026-05-04
**Archivos:**
- `dashboard/app.py` — FastAPI + WebSocket server.
- `dashboard/static/{index.html, app.js, styles.css}` — SPA mobile-responsive.
- `dashboard/Dockerfile` + `requirements.txt` — empaqueta el dashboard.
- `scripts/tunnel_phone.ps1` — expone al celular (LAN | cloudflared | ngrok).

---

## Endpoints

| Método | Ruta | Devuelve |
|---|---|---|
| GET | `/` | SPA (mobile-friendly) |
| GET | `/api/zones` | Resumen por zona (8 entradas) |
| GET | `/api/devices` | Lista plana de dispositivos |
| GET | `/api/metrics/live` | Snapshot actual (pps, bps, by_zone, ataques activos) |
| GET | `/api/attacks/recent?limit=20` | Últimos manifests `attack_*.json` |
| GET | `/api/models/metrics` | Métricas de los 5 modelos |
| WS | `/ws/feed` | Stream `{ts, type:"tick", payload:<live>}` cada 1s |

---

## SPA — vistas

1. **KPIs en cabecera:** pps total, bps total, zonas, dispositivos, ataques activos (rojo si > 0).
2. **Mapa de zonas:** card por zona con barra de actividad. Borde rojo si hay ataque.
3. **Ataques recientes:** tabla últimas 20 entradas (label, familia, inicio, duración).
4. **Modelos ML:** accuracy/precision/recall/F1/train(s) por modelo.
5. **Dispositivos:** tabla filtrable (~70 entradas).

Mobile-first: `viewport`, grid `auto-fit minmax(220px, 1fr)`, tipografía base 14px, breakpoints en 480px.

---

## Acceso desde celular

### Opción 1 — LAN (recomendada)

```powershell
.\scripts\tunnel_phone.ps1 lan
```

Detecta IP LAN, abre regla de firewall, imprime URL `http://<IP>:8000`. PC y celular en mismo Wi-Fi.

### Opción 2 — Cloudflare Tunnel (sin abrir router)

```powershell
.\scripts\tunnel_phone.ps1 cloudflared
```

Si no está: `winget install --id Cloudflare.cloudflared`. Imprime URL `https://<...>.trycloudflare.com`. Funciona desde **cualquier red** del celular (datos móviles).

### Opción 3 — ngrok

```powershell
.\scripts\tunnel_phone.ps1 ngrok
```

Igual que cloudflared pero requiere cuenta gratuita ngrok.

---

## Modo demo (sin Mininet corriendo)

Si no hay PCAP ni `/tmp/iot_hosts.json`, el dashboard genera **valores sintéticos** basados en `zones.yaml` (rate_pps declarado × jitter ±15%). Permite probar la UI sin levantar Mininet.

---

## Cómo correr

```powershell
cd C:\Users\mquui\iot-sdn-ai
pip install -r dashboard\requirements.txt
python dashboard\app.py
```

Abrir `http://localhost:8000` en navegador. WebSocket se conecta automático.

---

## Tradeoffs

- **Modelos NO se cargan en `app.py`** todavía. Deliberado: la inferencia en vivo (cargar `rf.joblib`, predecir desde flujos en streaming) es trabajo de PASO-09 con Prometheus pull. Mantener `app.py` ligero permite desplegarlo aislado sin pesar deps de scikit-learn.
- **WebSocket en proceso único:** suficiente para 1-10 clientes. Para >50 clientes habría que mover a Redis pub/sub. Out of scope.
- **Sin auth:** lab cerrado. Si se expone públicamente con tunnel, añadir `Basic-Auth` middleware o restringir IPs.

---

## Próximo paso

`PASO-09-grafana.md` — dashboard Grafana provisioned + alertas Prometheus.
