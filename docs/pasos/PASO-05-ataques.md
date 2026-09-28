# PASO 05 — Catálogo de ataques (14 escenarios)

**Fecha:** 2026-05-04
**Archivos:**
- `iot/attacks/catalog.yaml` — declaración de los 14 escenarios.
- `iot/attacks/runner.py` — lanzador único.
- `iot/attacks/scenarios/*.py` — implementación por escenario.

---

## Catálogo

| # | id | familia | etiqueta dataset | herramienta |
|---|---|---|---|---|
| 1 | `syn_flood` | ddos | `SYN_FLOOD` | hping3 / raw socket |
| 2 | `udp_flood` | ddos | `UDP_FLOOD` | stdlib socket |
| 3 | `icmp_flood` | ddos | `ICMP_FLOOD` | hping3 / ping -f |
| 4 | `http_flood` | ddos | `HTTP_FLOOD` | stdlib threads |
| 5 | `slowloris` | dos_low_rate | `SLOWLORIS` | stdlib socket |
| 6 | `port_scan` | recon | `PORT_SCAN` | nmap / TCP connect |
| 7 | `arp_spoof` | mitm | `ARP_SPOOF` | scapy / AF_PACKET |
| 8 | `dns_amplification` | amplification | `DNS_AMPLIFICATION` | raw socket |
| 9 | `coap_amplification` | amplification | `COAP_AMPLIFICATION` | raw socket |
| 10 | `ssdp_amplification` | amplification | `SSDP_AMPLIFICATION` | raw socket |
| 11 | `mqtt_subscribe_flood` | protocol_abuse | `MQTT_SUBSCRIBE_FLOOD` | stdlib threads |
| 12 | `mqtt_malformed` | protocol_abuse | `MQTT_MALFORMED` | stdlib socket |
| 13 | `credential_bruteforce` | bruteforce | `CREDENTIAL_BRUTEFORCE` | stdlib socket |
| 14 | `mirai_coordinated` | botnet_ddos | `MIRAI_COORDINATED` | hping3 multi-bot |

---

## Lanzamiento

### Listar:
```bash
docker compose exec mininet python3 /root/iot/attacks/runner.py --list
```

### Lanzar uno:
```bash
docker compose exec mininet mn -c    # limpia
make iot-up                           # topología arriba con tráfico benigno
docker compose exec mininet python3 /root/iot/attacks/runner.py --scenario syn_flood --duration 60
```

### Suite completa (PASO-10): `make iot-attack-all` corre los 14 escenarios secuenciales con 30s de cool-down entre ellos. Total ~25 minutos.

---

## Manifest por ataque

`runner.py` escribe `/tmp/attack_<ts>_<id>.json` con:

```json
{
  "scenario": "syn_flood",
  "label": "SYN_FLOOD",
  "family": "ddos",
  "started_at": 1746367200.123,
  "finished_at": 1746367260.456,
  "config": {...},
  "return_code": 0
}
```

El **labeler** del pipeline (PASO-06) usa esos timestamps para etiquetar paquetes capturados durante la ventana del ataque.

---

## Quién lanza cada ataque

- **13 ataques desde `attacker` (10.10.0.99)** — host único en zona infra. Limpio en el dataset: cualquier tráfico desde esa IP en una ventana de manifest = ataque.
- **`mirai_coordinated`** — usa 5 dispositivos IoT como bots (`cam_front`, `cam_back`, `bulb_living`, `smart_plug_a`, `vacuum`). Espeja botnet realista: el atacante NO es el origen, lo son víctimas comprometidas. Más difícil de detectar — útil para evaluar robustez de los modelos.

---

## Tradeoffs y riesgos

- **Mininet en Docker no permite ARP spoof entre namespaces sin trucos**: `arp_spoof.py` requiere `AF_PACKET` y bridge en modo promiscuo. Si falla, el manifest queda con `return_code=1` y se omite del entrenamiento.
- **Raw sockets requieren root**: el container Mininet ya corre privilegiado. Fuera de Mininet (host Windows/WSL) muchos ataques no funcionan. Documentado en cada script.
- **Tasas declaradas son intentos**: el throughput real depende del CPU host y kernel de Mininet. En lab típico se obtiene ~30-60% del rate declarado. Aceptable: el dataset captura lo que la red **realmente vio**, no la intención.

---

## Próximo paso

`PASO-06-pipeline.md` — captura, extracción de features, etiquetado.
