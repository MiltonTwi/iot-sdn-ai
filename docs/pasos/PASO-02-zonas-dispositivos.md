# PASO 02 — Catálogo de zonas y dispositivos IoT

**Fecha:** 2026-05-04
**Archivo fuente:** `iot/zones.yaml`
**Total:** 7 zonas + 1 zona infraestructura, **63 dispositivos IoT** + 7 servidores.

---

## Resumen

| Zona | id | Subred | Dispositivos | Foco |
|---|---|---|---|---|
| Smart Home | 1 | 10.10.1.0/24 | 15 | Cámaras, bombillas, termostato, voz |
| Industrial (IIoT) | 2 | 10.10.2.0/24 | 12 | PLCs, SCADA, sensores planta |
| Healthcare | 3 | 10.10.3.0/24 | 8 | Monitores paciente, ECG, bombas |
| Smart City | 4 | 10.10.4.0/24 | 8 | Tráfico, parking, CCTV, EV |
| Wearables | 5 | 10.10.5.0/24 | 6 | Reloj, banda, GPS, AR |
| Agriculture | 6 | 10.10.6.0/24 | 6 | Suelo, clima, drone, ganado |
| Retail | 7 | 10.10.7.0/24 | 5 | POS, RFID, beacons |
| **Infra (servers)** | 0 | 10.10.0.0/24 | 7 | MQTT broker, CoAP, DNS, NTP, HTTP, SSDP, attacker |

---

## Distribución por protocolo

| Protocolo | Dispositivos | Uso |
|---|---|---|
| `mqtt-pub` | 30 | Telemetría periódica (sensores, plugs, lights) |
| `udp-stream` | 8 | Cámaras, ECG, AR glasses, drone — flujo constante alto pps |
| `http-post` | 6 | Wearables, POS, voz, EV charger — JSON telemetría |
| `coap` | 7 | Healthcare crítico, parking, irrigación — UDP+CoAP |
| `tcp-modbus` | 4 | PLCs, robot, conveyor — control industrial |
| `http-poll` | 4 | SCADA, TV, signage — pull periódico |

Mezcla deliberada: protocolos texto/binarios, TCP/UDP, alto/bajo pps. Permite que los modelos ML aprendan patrones diferenciables y los ataques tengan superficie variada.

---

## Razones de diseño

- **63 dispositivos** = volumen suficiente para entrenamiento ML estable (>10⁶ flujos en pocos minutos), sin saturar Mininet (probado hasta ~200 hosts en spine-leaf).
- **Subred por zona**: aisla broadcast/ARP, permite reglas SDN por zona, simplifica etiquetado.
- **Servidores en zona 0**: punto único de focalización para ataques de amplificación y floods.
- **Attacker en `10.10.0.99`**: host malicioso fijo, fácil de identificar en el dataset.
- **Tasas pps realistas**: cámaras 30-60 pps, sensores 0.1-2 pps, PLCs 5-10 pps. Espejan tráfico observado en datasets reales (CIC-IoT-2023, IoT-23).

---

## Cómo extender

Añadir un dispositivo: editar `iot/zones.yaml`, agregar entrada en la zona deseada con `name/ip/type/proto/dst/rate_pps/payload`. Regenerar topología: `python iot/topology/generate_topology.py`.

Añadir una zona: agregar bloque completo bajo `zones:`, con `id` único (>=8). Asignar subred `10.10.{id}.0/24`. Reservar leaf-switch `s_iot_{id}`.

---

## Próximo paso

`PASO-03-topologia.md` — generador de topología Mininet desde este YAML.
