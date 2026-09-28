#!/usr/bin/env python3
"""
Cap por clase con reservoir sampling en UNA pasada (memoria acotada).

Necesario porque el dataset crudo tiene millones de filas (floods) y cargarlo
entero en RAM revienta la VM. Mantiene <=cap filas por clase (muestreo uniforme
sin sesgo, seed fija) mientras solo conserva en memoria las filas retenidas.

uso: cap_dataset.py <dataset.csv> [cap]   (edita el archivo in-place)
"""
from __future__ import annotations

import collections
import random
import sys


def main() -> None:
    path = sys.argv[1]
    cap = int(sys.argv[2]) if len(sys.argv) > 2 else 50000
    random.seed(42)

    with open(path, encoding="utf-8") as f:
        header = f.readline()
        cols = header.rstrip("\n").split(",")
        li = cols.index("label")
        res: dict[str, list[str]] = collections.defaultdict(list)
        cnt: dict[str, int] = collections.defaultdict(int)
        total = 0
        for line in f:
            total += 1
            lab = line.split(",")[li]
            cnt[lab] += 1
            bucket = res[lab]
            if len(bucket) < cap:
                bucket.append(line)
            else:
                j = random.randint(0, cnt[lab] - 1)
                if j < cap:
                    bucket[j] = line

    kept = [ln for b in res.values() for ln in b]
    random.shuffle(kept)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(header)
        f.writelines(kept)

    print(f"cap={cap}: {total} -> {len(kept)} filas ({len(res)} clases)")
    for lab, c in sorted(cnt.items(), key=lambda kv: -kv[1]):
        print(f"  {lab:<24}{min(c, cap):>8}  (de {c})")


if __name__ == "__main__":
    main()
