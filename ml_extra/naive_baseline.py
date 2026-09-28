#!/usr/bin/env python3
"""
Detector naive basado en reglas. Sirve como baseline para justificar el ML.

Reglas:
  - DDoS:   tot_pkts > 5000 EN un flujo, O host_pkts_5s > 10000
  - Scan:   host_distinct_dport_5s > 10
  - Amplif: down_up_ratio > 50
  - Brute:  host_flows_5s > 100 con dst_port en {22, 23, 2323}
  - Resto:  BENIGN

Uso:
  python ml_extra/naive_baseline.py --dataset data/processed/run/dataset.csv
  → reporta accuracy + classification_report
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, f1_score


def predict_naive(df: pd.DataFrame) -> np.ndarray:
    n = len(df)
    out = np.array(["BENIGN"] * n, dtype=object)
    pkts = df["tot_pkts"].astype(float).values
    host_pkts = df.get("host_pkts_5s", pd.Series([0] * n)).astype(float).values
    host_dport = df.get("host_distinct_dport_5s", pd.Series([0] * n)).astype(float).values
    host_flows = df.get("host_flows_5s", pd.Series([0] * n)).astype(float).values
    down_up = df.get("down_up_ratio", pd.Series([0] * n)).astype(float).values
    syn = df.get("syn_count", pd.Series([0] * n)).astype(float).values
    dst_port = df["dst_port"].astype(int).values

    # Orden importa: lo más específico primero
    out[host_dport > 10] = "PORT_SCAN"
    out[(host_flows > 100) & np.isin(dst_port, [22, 23, 2323])] = "CREDENTIAL_BRUTEFORCE"
    out[down_up > 50] = "DNS_AMPLIFICATION"
    out[(pkts > 5000) | (host_pkts > 10000)] = "SYN_FLOOD"  # genérico para DDoS
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    df = pd.read_csv(args.dataset)
    if "label" not in df.columns:
        print("dataset sin label", file=sys.stderr); sys.exit(1)

    y_true = df["label"].values
    y_pred = predict_naive(df)

    # Para comparación honesta: agrupar todos los floods en SYN_FLOOD del baseline
    # Re-mapeamos y_true para colapsar familias DDoS:
    ddos_labels = {"SYN_FLOOD", "UDP_FLOOD", "ICMP_FLOOD", "HTTP_FLOOD", "MIRAI_COORDINATED"}
    y_true_grouped = np.where(np.isin(y_true, list(ddos_labels)), "SYN_FLOOD", y_true)

    acc = accuracy_score(y_true_grouped, y_pred)
    f1 = f1_score(y_true_grouped, y_pred, average="macro", zero_division=0)
    print(f"naive baseline:  accuracy={acc:.4f}  f1_macro={f1:.4f}")
    print()
    print(classification_report(y_true_grouped, y_pred, zero_division=0))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        import json
        args.out.write_text(json.dumps({
            "model": "naive_rule_based",
            "accuracy": float(acc),
            "f1_macro": float(f1),
            "rules": [
                "host_distinct_dport_5s > 10 → PORT_SCAN",
                "host_flows_5s > 100 ∧ dst_port ∈ {22,23,2323} → BRUTEFORCE",
                "down_up_ratio > 50 → AMPLIFICATION",
                "tot_pkts > 5000 ∨ host_pkts_5s > 10000 → DDoS (SYN_FLOOD)",
            ]
        }, indent=2))
        print(f"\nReporte: {args.out}")


if __name__ == "__main__":
    main()
