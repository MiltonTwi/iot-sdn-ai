#!/usr/bin/env python3
"""Genera dataset sintético para validar el pipeline ML sin Mininet.

Produce filas con las MISMAS columnas que el pipeline real (flow_extractor +
label_dataset + feature_engineering), con distribuciones por etiqueta que
permiten al modelo aprender (signal real, no ruido puro).
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path


COLUMNS = [
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
    "label", "attack_family", "src_zone", "dst_zone", "src_device_type",
]


PROFILES = {
    # label: (weight, mean_pps, mean_bytes, syn_ratio, down_up, dport, indicator, host_flows_5s, family)
    "BENIGN":               (40, 5,    300,   0.05, 0.5,  [80, 1883, 5683], "is_mqtt",   3,   "benign"),
    "SYN_FLOOD":            (15, 8000, 60,    0.95, 0.0,  [80, 443],         "is_http",   200, "ddos"),
    "UDP_FLOOD":            (12, 6000, 800,   0.0,  0.0,  [5683, 53],        "is_coap",   180, "ddos"),
    "ICMP_FLOOD":           (8,  4000, 64,    0.0,  0.0,  [0],               None,        150, "ddos"),
    "HTTP_FLOOD":           (6,  500,  400,   0.3,  0.1,  [80],              "is_http",   100, "ddos"),
    "PORT_SCAN":            (5,  20,   60,    0.9,  0.05, [22, 80, 502, 1883, 5683], None, 300, "recon"),
    "DNS_AMPLIFICATION":    (4,  3000, 90,    0.0,  100.0, [53],             "is_dns",    120, "amplification"),
    "MQTT_SUBSCRIBE_FLOOD": (5,  300,  150,   0.4,  0.05, [1883],            "is_mqtt",   80,  "protocol_abuse"),
    "CREDENTIAL_BRUTEFORCE":(3,  50,   100,   0.5,  0.1,  [22, 23, 2323],    None,        250, "bruteforce"),
    "SLOWLORIS":            (2,  3,    50,    0.05, 0.0,  [80],              "is_http",   500, "dos_low_rate"),
}

INDICATORS = ["is_mqtt", "is_coap", "is_modbus", "is_dns", "is_ntp", "is_ssdp", "is_http"]


def gen_row(label: str, idx: int, ts: float) -> dict:
    weight, mean_pps, mean_bytes, syn_ratio, down_up, dports, indicator, host_flows, family = PROFILES[label]
    pps = max(0.1, random.gauss(mean_pps, mean_pps * 0.2))
    duration = random.uniform(1, 30)
    tot_pkts = max(1, int(pps * duration))
    tot_bytes = int(tot_pkts * max(20, random.gauss(mean_bytes, mean_bytes * 0.3)))
    fwd_pkts = int(tot_pkts * (1 / (1 + down_up)) if down_up < 50 else tot_pkts // (1 + 0.001))
    bwd_pkts = max(0, tot_pkts - fwd_pkts)
    fwd_bytes = int(tot_bytes * (1 / (1 + down_up)))
    bwd_bytes = max(0, tot_bytes - fwd_bytes)
    syn = int(tot_pkts * syn_ratio * random.uniform(0.8, 1.2))

    dport = random.choice(dports) if dports else random.randint(1024, 65535)
    proto = 1 if dport == 0 else (17 if dport in (53, 5683, 123, 1900) else 6)
    src_ip = f"10.10.{random.randint(0, 7)}.{random.randint(10, 99)}"
    dst_ip = f"10.10.0.{random.choice([10, 11, 12, 13, 14, 15])}"
    if label != "BENIGN":
        if family == "amplification":
            src_ip = "10.10.0.99"  # spoof attacker
        elif label.startswith(("SYN", "UDP", "ICMP", "HTTP", "MQTT", "CREDENTIAL", "SLOW")):
            src_ip = "10.10.0.99"

    fwd_mean = max(20, random.gauss(mean_bytes, mean_bytes * 0.1))
    bwd_mean = max(20, random.gauss(mean_bytes * (down_up + 0.5), mean_bytes * 0.2)) if bwd_pkts else 0

    row = {
        "src_ip": src_ip, "dst_ip": dst_ip,
        "src_port": random.randint(1024, 65535), "dst_port": dport, "proto": proto,
        "start_ts": ts, "duration": round(duration, 3),
        "tot_fwd_pkts": fwd_pkts, "tot_bwd_pkts": bwd_pkts, "tot_pkts": tot_pkts,
        "tot_fwd_bytes": fwd_bytes, "tot_bwd_bytes": bwd_bytes, "tot_bytes": tot_bytes,
        "fwd_pkt_len_mean": round(fwd_mean, 1), "fwd_pkt_len_std": round(fwd_mean * 0.1, 1),
        "fwd_pkt_len_max": int(fwd_mean * 1.4), "fwd_pkt_len_min": max(20, int(fwd_mean * 0.7)),
        "bwd_pkt_len_mean": round(bwd_mean, 1), "bwd_pkt_len_std": round(bwd_mean * 0.1, 1),
        "bwd_pkt_len_max": int(bwd_mean * 1.4) if bwd_mean else 0,
        "bwd_pkt_len_min": max(20, int(bwd_mean * 0.7)) if bwd_mean else 0,
        "iat_mean": round(1.0 / pps, 4), "iat_std": round(0.1 / pps, 4),
        "iat_max": round(2.0 / pps, 4), "iat_min": round(0.5 / pps, 4),
        "fwd_iat_mean": round(1.0 / pps, 4), "bwd_iat_mean": round(1.5 / pps, 4) if bwd_pkts else 0,
        "syn_count": syn, "fin_count": int(syn * 0.05), "rst_count": int(syn * 0.02),
        "psh_count": int(tot_pkts * 0.1), "ack_count": int(tot_pkts * 0.7),
        "urg_count": 0,
        "fwd_pps": round(fwd_pkts / duration, 1), "bwd_pps": round(bwd_pkts / duration, 1),
        "down_up_ratio": round(bwd_bytes / max(fwd_bytes, 1), 3),
        "byte_entropy": round(random.uniform(0.5, 4.5), 2),
    }
    for ind in INDICATORS:
        row[ind] = 0
    if indicator:
        row[indicator] = 1
    elif dport in (502,):
        row["is_modbus"] = 1

    row["host_flows_5s"] = max(1, int(random.gauss(host_flows, host_flows * 0.2)))
    row["host_distinct_dst_5s"] = min(row["host_flows_5s"], random.randint(1, 20)) if "SCAN" not in label else random.randint(20, 200)
    row["host_distinct_dport_5s"] = min(row["host_flows_5s"], random.randint(1, 5)) if "SCAN" not in label else random.randint(5, 30)
    row["host_pkts_5s"] = row["host_flows_5s"] * tot_pkts // max(1, fwd_pkts) * 5
    row["host_bytes_5s"] = row["host_pkts_5s"] * int(fwd_mean)
    row["host_syn_5s"] = row["host_flows_5s"] * syn // max(1, tot_pkts) * 5
    row["host_syn_ratio"] = round(row["host_syn_5s"] / max(1, row["host_pkts_5s"]), 3)

    row["label"] = label
    row["attack_family"] = family
    row["src_zone"] = "smart_home" if src_ip.startswith("10.10.1") else ("infra" if src_ip.startswith("10.10.0") else "industrial")
    row["dst_zone"] = "infra"
    row["src_device_type"] = "attacker" if src_ip == "10.10.0.99" else random.choice(["camera", "sensor_temp", "plc", "smart_bulb"])
    return row


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--n", type=int, default=5000)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    random.seed(args.seed)
    weights = [(label, w) for label, (w, *_) in PROFILES.items()]
    total_w = sum(w for _, w in weights)
    counts = {label: max(1, args.n * w // total_w) for label, w in weights}

    rows = []
    ts = 1_700_000_000.0
    for label, n in counts.items():
        for i in range(n):
            rows.append(gen_row(label, i, ts))
            ts += random.uniform(0.001, 0.5)
    random.shuffle(rows)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)

    print(f"Generadas {len(rows)} filas → {args.out}")
    for label, n in counts.items():
        print(f"  {label:<24} {n}")


if __name__ == "__main__":
    main()
