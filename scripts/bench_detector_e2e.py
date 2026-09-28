#!/usr/bin/env python3
"""
Mide latencia del componente Detector aislado: por cada src_ip atacante,
cuánto tarda desde que su PRIMERA fila aparece en el stream hasta que
detector_service.Detector.react() emite la POST /iot/mitigate.

NO mide ventana de captura ni lag de flow_extractor — solo el componente
de decisión + REST. Combinar con los 60ms ya medidos para tener el camino
detector→OVS completo.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dashboard.detector_service import Detector  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--controller", default="http://localhost:8080")
    p.add_argument("--artifacts", type=Path, default=ROOT / "ml_extra" / "artifacts")
    p.add_argument("--limit", type=int, default=0, help="0 = todas las filas")
    args = p.parse_args()

    det = Detector(args.artifacts, args.controller)
    det.cooldown_s = 0
    print(f"[init] modelo cargado ({len(det.classes)} clases)")

    seen_ips: dict[str, dict] = {}
    n = 0
    t_start = time.perf_counter()

    with args.csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            n += 1
            src = row.get("src_ip", "")
            if not src or src in seen_ips:
                if seen_ips.get(src, {}).get("done"):
                    continue
            t_in = time.perf_counter()
            label, conf = det.predict_row(row)
            t_decide = time.perf_counter()

            entry = seen_ips.get(src)
            if entry is None:
                seen_ips[src] = {"first_in": t_in, "label": label, "done": False}
                entry = seen_ips[src]

            if entry["done"]:
                continue

            resp = det.react(src, label, conf)
            t_react = time.perf_counter()

            if resp is not None:
                entry["t_decide_ms"] = (t_decide - entry["first_in"]) * 1000
                entry["t_react_ms"] = (t_react - entry["first_in"]) * 1000
                entry["mitigated_label"] = label
                entry["done"] = True

            if args.limit and n >= args.limit:
                break

    elapsed = time.perf_counter() - t_start
    print(f"[done] {n} filas procesadas en {elapsed:.1f}s — {n/elapsed:.0f} filas/s")

    mitigated = [e for e in seen_ips.values() if e.get("done")]
    print(f"[done] {len(seen_ips)} IPs únicas vistas, {len(mitigated)} dispararon mitigate")

    if mitigated:
        decide_ms = [e["t_decide_ms"] for e in mitigated]
        react_ms = [e["t_react_ms"] for e in mitigated]
        print()
        print(f"  {'etapa':<22}  {'mean':>8}  {'p50':>8}  {'p95':>8}  {'min':>8}  {'max':>8}")
        for name, vals in [
            ("decide (predict)", decide_ms),
            ("react (predict+REST)", react_ms),
        ]:
            print(
                f"  {name:<22}  {statistics.mean(vals):>7.2f}ms  "
                f"{statistics.median(vals):>7.2f}ms  "
                f"{np.quantile(vals, 0.95):>7.2f}ms  "
                f"{min(vals):>7.2f}ms  {max(vals):>7.2f}ms"
            )

        labels = {}
        for e in mitigated:
            labels.setdefault(e["mitigated_label"], 0)
            labels[e["mitigated_label"]] += 1
        print(f"\n  por clase mitigada:")
        for lbl, c in sorted(labels.items(), key=lambda x: -x[1]):
            print(f"    {lbl:<25} {c}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
