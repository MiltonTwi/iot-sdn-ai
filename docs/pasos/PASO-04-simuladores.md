# PASO 04 — Simuladores de dispositivos IoT

**Fecha:** 2026-05-04
**Archivos:**
- `iot/devices/runner.py` — un único proceso por host, despacha por `--proto`.
- `iot/devices/servers/{mqtt_broker, coap_server, dns_server, ntp_server, ssdp_server}.py` — servidores en zona infra.

---

## Decisión clave

**Stdlib pura. Sin deps externas.** El container Mininet del repo base trae Python 3.8 y nada más. Cada paquete extra es trabajo de imagen + tiempo de build.

Implementación de protocolos a mano:

| Protocolo | Líneas RFC implementadas | Por qué basta |
|---|---|---|
| MQTT 3.1.1 | CONNECT + CONNACK + PUBLISH QoS0 | El dataset solo necesita el flujo TCP/1883 con frames distinguibles |
| CoAP | CON GET, ACK 2.05 Content | Protocolo binario UDP/5683 de 4-byte header — trivial |
| Modbus/TCP | MBAP + read-holding-registers (FC 03) | Frame fijo de 12 bytes, perfecto para identificar IIoT |
| HTTP/1.1 | GET + POST con `Connection: close` | Stdlib + raw socket, ningún cliente adicional |
| UDP-stream | sendto() de blob fijo | Espeja video/sensor stream sin codec |
| DNS, NTP, SSDP | Respuestas fijas con padding largo | Necesarias como reflectores para ataques de amplificación |

---

## Flujo de un host

```
mn_iot_topo.py (en container mininet)
  └─▶ host.cmd("python3 /root/iot/devices/runner.py --name cam_front --proto udp-stream --dst-name http_server --rate 50 --payload 1200 --zone smart_home &")

runner.py
  ├─ time.sleep(jitter [0,2]s)   ← desincroniza arranques
  └─ DISPATCH[args.proto](args)  ← bucle infinito de envío
```

El **jitter inicial** (0..2s) evita que 63 hosts envíen paquetes en el mismo instante (rebanada de pps sincrónica produciría artefactos en el dataset).

---

## Servidores en zona infra (10.10.0.0/24)

| Host | IP | Puerto | Función |
|---|---|---|---|
| mqtt_broker | 10.10.0.10 | 1883 TCP | Acepta CONNECT, ack, recibe PUBLISH (descarta) |
| coap_server | 10.10.0.11 | 5683 UDP | ACK 2.05 a cualquier GET |
| http_server | 10.10.0.12 | 80 TCP | `python3 -m http.server` (stdlib) |
| dns_server | 10.10.0.13 | 53 UDP | Responde TXT con padding 256B (reflector amplificación) |
| ntp_server | 10.10.0.14 | 123 UDP | Mode 4, 48B (queryable para amplif. NTP) |
| ssdp_server | 10.10.0.15 | 1900 UDP | M-SEARCH → respuesta ~400B (reflector SSDP) |

Los reflectores DNS/NTP/SSDP están **a propósito** configurados con respuestas grandes — sin eso los ataques de amplificación tendrían factor 1x y serían indistinguibles de tráfico normal.

---

## Trazabilidad en el dataset

Cada paquete enviado lleva metadata útil para el etiquetado:

- IP origen → identifica zona y dispositivo (rango `10.10.{zone}.{idx}`).
- Puerto destino → identifica protocolo (1883 MQTT, 5683 CoAP, 502 Modbus, etc.).
- Payload size → coincide con `payload` declarado en `zones.yaml`.
- Tasa pps → coincide con `rate_pps`.

El extractor de features (PASO-06) cruza estos campos con `zones.yaml` para etiquetar tráfico **BENIGN** vs ataque.

---

## Probar un simulador suelto (sin Mininet)

```powershell
# en host Windows, contra cualquier broker MQTT local
python iot\devices\runner.py --name test_dev --proto mqtt-pub --dst-name mqtt_broker --rate 1 --payload 100 --zone smart_home
```

Necesita ajustar `SERVERS["mqtt_broker"]` a una IP real, o levantar `python iot\devices\servers\mqtt_broker.py` en otra terminal.

---

## Próximo paso

`PASO-05-ataques.md` — catálogo de 12+ ataques con scripts ejecutables.
