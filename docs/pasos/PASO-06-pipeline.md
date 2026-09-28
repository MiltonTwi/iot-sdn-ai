# PASO 06 — Pipeline de datos IoT-aware

**Fecha:** 2026-05-04
**Archivos:**
- `iot/pipeline/flow_extractor.py` — PCAP → flujos (CSV).
- `iot/pipeline/label_dataset.py` — cruza con manifests de ataques + zones.yaml.
- `iot/pipeline/feature_engineering.py` — agregados por host/ventana 5s.

---

## Tubería

```
captura tshark        →  data/raw/{run}/capture.pcap
flow_extractor.py     →  data/processed/{run}/flows.csv
label_dataset.py      →  data/processed/{run}/flows_labeled.csv
feature_engineering   →  data/processed/{run}/dataset.csv      ← entrada al ML
```

**Decisión:** PCAP parser **stdlib propio** (no scapy/dpkt). Razón: el container Mininet trae Python 3.8 sin deps. Implementación: ~80 líneas, IPv4/TCP/UDP/ICMP, suficiente para Mininet (no maneja VLAN, IPv6, fragmentación — innecesario en lab).

---

## Features por flujo (38 columnas + 7 host_*)

Bloques temáticos:

| Bloque | Columnas | Por qué |
|---|---|---|
| Identificación | src_ip, dst_ip, src_port, dst_port, proto | Joins, debugging, no entran al modelo (feature-leakage) |
| Volumen | tot_pkts, tot_fwd_pkts, tot_bwd_pkts, tot_bytes, ... | Floods se ven aquí inmediatamente |
| Tamaño paquete | fwd_pkt_len_{mean,std,max,min}, bwd_* | Distingue cámaras (1200B fijos) de control (80B) |
| Tiempo / IAT | iat_{mean,std,max,min}, fwd_iat_mean, bwd_iat_mean | Patrón periódico de IoT vs ráfaga DDoS |
| Flags TCP | syn/fin/rst/psh/ack/urg counts | SYN-flood = SYN sin ACK, slowloris = pocos PSH |
| Tasas | fwd_pps, bwd_pps, down_up_ratio | Amplification = ratio enorme (0.001 query → 256B reply) |
| Entropía | byte_entropy | Tráfico cifrado vs payloads predecibles |
| Indicadores protocolo | is_mqtt/is_coap/is_modbus/is_dns/is_ntp/is_ssdp/is_http | Sesgo correcto del modelo por familia de protocolo |
| Host-window 5s | host_flows_5s, host_distinct_dst/dport_5s, host_pkts/bytes/syn_5s, host_syn_ratio | Detecta port-scan y bruteforce que un solo flow no revela |

---

## Etiquetado: por qué cruzar contra manifests

El **labeler** **no usa heurísticas frágiles** (ej. "todo flujo con >1000 SYN/s = ataque"). Eso filtra mal y produce datasets sesgados.

En su lugar, cruza:
1. **Ventana temporal** del manifest (`started_at..finished_at`) producido por `iot/attacks/runner.py`.
2. **IP del atacante** (10.10.0.99) o **IP víctima** (target_ip / reflector_ip) involucradas en el flujo.

Garantía: durante una sesión "BENIGN" (sin manifests), todos los flujos quedan `BENIGN`. Durante un ataque, solo los flujos directamente conectados al ataque heredan la etiqueta — el tráfico IoT periódico de fondo permanece `BENIGN`. Esto produce un dataset **mixto** y realista, no uno estilo "todo ataque".

---

## Cómo correr el pipeline completo

```bash
# 1) capturar (mientras corre el ataque)
docker compose exec mininet tshark -i s_spine_1-eth1 -w /root/data/raw/run_001/capture.pcap

# 2) extractor (host Windows o WSL — Python 3.10+)
python iot\pipeline\flow_extractor.py \
    --pcap data\raw\run_001\capture.pcap \
    --out data\processed\run_001\flows.csv

# 3) etiquetar
python iot\pipeline\label_dataset.py \
    --flows data\processed\run_001\flows.csv \
    --manifests data\raw\run_001\ \
    --out data\processed\run_001\flows_labeled.csv

# 4) feature engineering
python iot\pipeline\feature_engineering.py \
    --inp data\processed\run_001\flows_labeled.csv \
    --out data\processed\run_001\dataset.csv
```

`make iot-pipeline RUN=run_001` automatiza los 4 pasos (PASO-10).

---

## Volumen esperado

Con 63 dispositivos a tasas declaradas, **~3,000 paquetes/s benigno** sostenido. Una corrida de 5 minutos benigna + 25 minutos con 14 ataques (2 min cada uno) produce:

- ~600,000 paquetes totales
- ~50,000 - 100,000 flujos
- ~30 MB de PCAP
- ~15 MB de CSV final

Suficiente para entrenar 5 modelos sin overfit grosero. Para ampliar dataset, repetir corridas: cada `run_id` se concatena con `pandas.concat`.

---

## Próximo paso

`PASO-07-modelos-ml.md` — entrenamiento y comparativa de 5 modelos.
