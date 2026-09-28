#!/usr/bin/env python3
"""Imprime tabla comparativa de los 5 modelos desde artifacts/metrics.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--metrics", type=Path,
        default=Path(__file__).resolve().parent / "artifacts" / "metrics.json",
    )
    args = p.parse_args()
    data = json.loads(args.metrics.read_text())

    print()
    print(f"{'modelo':<14} {'tipo':<14} {'accuracy':>10} {'precision':>10} {'recall':>10} {'f1_macro':>10} {'train(s)':>10}")
    print("-" * 90)
    for name, m in data.items():
        kind = m.get("type", "multiclass")
        print(
            f"{name:<14} {kind:<14} {m.get('accuracy', 0):>10.4f} "
            f"{m.get('precision_macro', 0):>10.4f} {m.get('recall_macro', 0):>10.4f} "
            f"{m.get('f1_macro', 0):>10.4f} {m.get('train_s', 0):>10.1f}"
        )
    print()


if __name__ == "__main__":
    main()
