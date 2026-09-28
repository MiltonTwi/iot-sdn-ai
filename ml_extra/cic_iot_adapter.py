#!/usr/bin/env python3
"""
Adapter para CIC-IoT-2023 → mismas features de nuestro pipeline.

Dataset: https://www.unb.ca/cic/datasets/iotdataset-2023.html  (~13 GB CSV)

Mapeo de columnas CIC → IoT-SDN-AI:
  CIC                          → IoT-SDN-AI
  ─────────────────────────────────────────────
  flow_duration                → duration
  Header_Length                → (descartado)
  Tot sum                      → tot_bytes
  Tot size                     → fwd_pkt_len_mean (aproximado)
  IAT                          → iat_mean
  Number                       → tot_pkts
  Magnitue                     → (descartado)
  Radius                       → (descartado)
  Covariance                   → iat_std (aproximado)
  Variance                     → iat_max (aproximado)
  Weight                       → (descartado)
  syn_flag_number              → syn_count
  fin_flag_number              → fin_count
  rst_flag_number              → rst_count
  ack_flag_number              → ack_count
  psh_flag_number              → psh_count
  HTTP, HTTPS, ...             → is_http (binario derivado)
  MQTT                         → is_mqtt
  TCP, UDP, ICMP               → proto (6, 17, 1)
  label                        → label (re-mapeado a nuestra taxonomía)

Uso:
  python ml_extra/cic_iot_adapter.py \\
      --inp <CIC_csv_or_dir> \\
      --out data/processed/cic_iot_2023/dataset.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


# Re-mapeo CIC labels → IoT-SDN-AI labels
LABEL_MAP = {
    "BenignTraffic":              "BENIGN",
    "Benign":                     "BENIGN",
    "DDoS-SYN_Flood":             "SYN_FLOOD",
    "DDoS-TCP_Flood":             "SYN_FLOOD",
    "DDoS-UDP_Flood":             "UDP_FLOOD",
    "DDoS-ICMP_Flood":            "ICMP_FLOOD",
    "DDoS-HTTP_Flood":            "HTTP_FLOOD",
    "DDoS-Slowloris":             "SLOWLORIS",
    "DDoS-RSTFINFlood":           "SYN_FLOOD",
    "DDoS-PSHACK_Flood":          "SYN_FLOOD",
    "DDoS-SYNonymousIP_Flood":    "SYN_FLOOD",
    "DDoS-ACK_Fragmentation":     "SYN_FLOOD",
    "DDoS-UDP_Fragmentation":     "UDP_FLOOD",
    "DDoS-ICMP_Fragmentation":    "ICMP_FLOOD",
    "DoS-SYN_Flood":              "SYN_FLOOD",
    "DoS-TCP_Flood":              "SYN_FLOOD",
    "DoS-UDP_Flood":              "UDP_FLOOD",
    "DoS-HTTP_Flood":             "HTTP_FLOOD",
    "Recon-PortScan":             "PORT_SCAN",
    "Recon-OSScan":               "PORT_SCAN",
    "Recon-VulnerabilityScan":    "PORT_SCAN",
    "Recon-PingSweep":            "PORT_SCAN",
    "Recon-HostDiscovery":        "PORT_SCAN",
    "MITM-ArpSpoofing":           "ARP_SPOOF",
    "DNS_Spoofing":               "DNS_AMPLIFICATION",
    "Mirai-greeth_flood":         "MIRAI_COORDINATED",
    "Mirai-greip_flood":          "MIRAI_COORDINATED",
    "Mirai-udpplain":             "MIRAI_COORDINATED",
    "BrowserHijacking":           "BENIGN",  # (no en nuestro catálogo)
    "Backdoor_Malware":           "BENIGN",
    "CommandInjection":           "BENIGN",
    "DictionaryBruteForce":       "CREDENTIAL_BRUTEFORCE",
    "SqlInjection":               "BENIGN",
    "Uploading_Attack":           "BENIGN",
    "VulnerabilityScan":          "PORT_SCAN",
    "XSS":                        "BENIGN",
}

# Columnas finales que produce el pipeline IoT-SDN-AI
TARGET_COLUMNS = [
    "src_ip", "dst_ip", "src_port", "dst_port", "proto",
    "start_ts", "duration",
    "tot_fwd_pkts", "tot_bwd_pkts", "tot_pkts",
    "tot_fwd_bytes", "tot_bwd_bytes", "tot_bytes",
    "fwd_pkt_len_mean", "fwd_pkt_len_std", "fwd_pkt_len_max", "fwd_pkt_len_min",
    "bwd_pkt_len_mean", "bwd_pkt_len_std", "bwd_pkt_len_max", "bwd_pkt_len_min",
    "iat_mean", "iat_std", "iat_max", "iat_min",
    "fwd_iat_mean", "bwd_iat_mean",
    "syn_count", "fin_count", "rst_count", "psh_count", "ack_count", "urg_count",
    "fwd_pps", "bwd_pps",
    "down_up_ratio", "byte_entropy",
    "is_mqtt", "is_coap", "is_modbus", "is_dns", "is_ntp", "is_ssdp", "is_http",
    "host_flows_5s", "host_distinct_dst_5s", "host_distinct_dport_5s",
    "host_pkts_5s", "host_bytes_5s", "host_syn_5s", "host_syn_ratio",
    "dst_flows_5s", "dst_distinct_src_5s", "dst_pkts_5s", "dst_bytes_5s",
    "label", "attack_family", "src_zone", "dst_zone", "src_device_type",
]

FAMILY_MAP = {
    "BENIGN": "benign",
    "SYN_FLOOD": "ddos", "UDP_FLOOD": "ddos", "ICMP_FLOOD": "ddos", "HTTP_FLOOD": "ddos",
    "SLOWLORIS": "dos_low_rate",
    "PORT_SCAN": "recon",
    "ARP_SPOOF": "mitm",
    "DNS_AMPLIFICATION": "amplification",
    "MQTT_SUBSCRIBE_FLOOD": "protocol_abuse",
    "CREDENTIAL_BRUTEFORCE": "bruteforce",
    "MIRAI_COORDINATED": "botnet_ddos",
}


def adapt_chunk(df: pd.DataFrame) -> pd.DataFrame:
    n = len(df)
    out = pd.DataFrame(index=range(n), columns=TARGET_COLUMNS, dtype=object)

    out["src_ip"] = "0.0.0.0"
    out["dst_ip"] = "0.0.0.0"
    out["src_port"] = _coerce_int(_get(df, "Src Port", 0))
    out["dst_port"] = _coerce_int(_get(df, "Dst Port", 0))
    # CIC "Protocol Type" puede venir como 1.0/6.0/17.0
    out["proto"] = _coerce_int(_get(df, "Protocol Type", _get(df, "TCP", 6)))

    out["start_ts"] = 0
    out["duration"] = _coerce_float(_get(df, "flow_duration", _get(df, "Duration", 0)))
    pkts = _coerce_int(_get(df, "Number", _get(df, "Packets", 1)))
    out["tot_pkts"] = pkts
    out["tot_fwd_pkts"] = pkts
    out["tot_bwd_pkts"] = 0

    bytes_total = _coerce_float(_get(df, "Tot sum", _get(df, "Tot Bytes", 0)))
    out["tot_bytes"] = bytes_total
    out["tot_fwd_bytes"] = bytes_total
    out["tot_bwd_bytes"] = 0

    avg_size = _coerce_float(_get(df, "Tot size", _get(df, "Avg Pkt Size", 0)))
    out["fwd_pkt_len_mean"] = avg_size
    out["fwd_pkt_len_std"] = _coerce_float(_get(df, "Variance", 0)) ** 0.5
    out["fwd_pkt_len_max"] = _coerce_float(_get(df, "Max", 0))
    out["fwd_pkt_len_min"] = _coerce_float(_get(df, "Min", 0))
    out[["bwd_pkt_len_mean", "bwd_pkt_len_std", "bwd_pkt_len_max", "bwd_pkt_len_min"]] = 0

    iat = _coerce_float(_get(df, "IAT", 0))
    out["iat_mean"] = iat
    out["iat_std"] = _coerce_float(_get(df, "Covariance", 0))
    out["iat_max"] = _coerce_float(_get(df, "Variance", 0))
    out["iat_min"] = iat * 0.5
    out["fwd_iat_mean"] = iat
    out["bwd_iat_mean"] = 0

    out["syn_count"] = _coerce_int(_get(df, "syn_flag_number", _get(df, "syn_count", 0)))
    out["fin_count"] = _coerce_int(_get(df, "fin_flag_number", _get(df, "fin_count", 0)))
    out["rst_count"] = _coerce_int(_get(df, "rst_flag_number", _get(df, "rst_count", 0)))
    out["psh_count"] = _coerce_int(_get(df, "psh_flag_number", 0))
    out["ack_count"] = _coerce_int(_get(df, "ack_flag_number", _get(df, "ack_count", 0)))
    out["urg_count"] = _coerce_int(_get(df, "urg_flag_number", 0))

    dur = out["duration"].astype(float).clip(lower=1e-6)
    out["fwd_pps"] = pkts.astype(float) / dur
    out["bwd_pps"] = 0
    out["down_up_ratio"] = 0
    out["byte_entropy"] = _coerce_float(_get(df, "Std", 0))

    out["is_http"]   = (_coerce_int(_get(df, "HTTP", 0)) | _coerce_int(_get(df, "HTTPS", 0))).astype(int)
    out["is_mqtt"]   = _coerce_int(_get(df, "MQTT", 0)).astype(int)
    out["is_coap"]   = 0
    out["is_modbus"] = 0
    out["is_dns"]    = _coerce_int(_get(df, "DNS", 0)).astype(int)
    out["is_ntp"]    = 0
    out["is_ssdp"]   = 0

    # host_* no se puede reconstruir con CIC (fila = flujo, no flujos por host).
    # Usamos placeholders 0; el modelo perderá esa señal pero podrá clasificar.
    # host_*/dst_* no se reconstruyen con CIC (fila=flujo). Placeholders 0; el
    # cross-eval válido usa --shared-features que los excluye del entrenamiento.
    for col in ["host_flows_5s", "host_distinct_dst_5s", "host_distinct_dport_5s",
                "host_pkts_5s", "host_bytes_5s", "host_syn_5s", "host_syn_ratio",
                "dst_flows_5s", "dst_distinct_src_5s", "dst_pkts_5s", "dst_bytes_5s"]:
        out[col] = 0

    raw_label = _get(df, "label", _get(df, "Label", "BenignTraffic")).astype(str)
    _norm_map = {k.lower().replace("-", "_"): v for k, v in LABEL_MAP.items()}
    out["label"] = raw_label.map(lambda l: _norm_map.get(l.lower().replace("-", "_"), "BENIGN"))
    out["attack_family"] = out["label"].map(FAMILY_MAP).fillna("benign")
    out["src_zone"] = "external"
    out["dst_zone"] = "external"
    out["src_device_type"] = "unknown"
    return out


def _coerce_int(s, n=None):
    if not isinstance(s, pd.Series):
        # Scalar fallback — return Series of zeros (or scalar value) of length n.
        if n is None:
            n = 1
        return pd.Series([int(s) if s is not None else 0] * n, dtype=int)
    return pd.to_numeric(s, errors="coerce").fillna(0).astype(int)


def _coerce_float(s, n=None):
    if not isinstance(s, pd.Series):
        if n is None:
            n = 1
        return pd.Series([float(s) if s is not None else 0.0] * n, dtype=float)
    return pd.to_numeric(s, errors="coerce").fillna(0).astype(float)


def _get(df, col, default):
    """Return df[col] if exists, else a Series of default with same length."""
    if col in df.columns:
        return df[col]
    if isinstance(default, pd.Series):
        return default
    return pd.Series([default] * len(df), index=df.index)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--inp", type=Path, required=True, help="CSV o carpeta de CSVs CIC-IoT-2023")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--max-rows", type=int, default=None, help="cap (debug)")
    args = p.parse_args()

    files: list[Path] = []
    if args.inp.is_dir():
        files = sorted(args.inp.glob("*.csv"))
    elif args.inp.is_file():
        files = [args.inp]
    if not files:
        print(f"sin CSVs en {args.inp}", file=sys.stderr); sys.exit(1)

    print(f"Procesando {len(files)} archivo(s)...")
    chunks = []
    rows_so_far = 0
    for f in files:
        for chunk in pd.read_csv(f, chunksize=200_000, low_memory=False):
            adapted = adapt_chunk(chunk)
            chunks.append(adapted)
            rows_so_far += len(adapted)
            if args.max_rows and rows_so_far >= args.max_rows:
                break
        if args.max_rows and rows_so_far >= args.max_rows:
            break

    df = pd.concat(chunks, ignore_index=True)
    if args.max_rows:
        df = df.head(args.max_rows)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)

    print(f"Salida: {args.out}  ({len(df)} filas)")
    print()
    print("Distribución de labels:")
    print(df["label"].value_counts().head(15).to_string())


if __name__ == "__main__":
    main()
