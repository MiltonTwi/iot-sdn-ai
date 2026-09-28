#!/usr/bin/env python3
"""Intervalo de confianza (bootstrap) del F1-macro sobre el hold-out fold-0.

Remuestrea con reemplazo el conjunto de prueba (grouped fold-0, el mismo que
vieron los modelos guardados) y recomputa F1-macro para estimar dispersión.
Complementa la desviación entre folds de la CV agrupada.

  python ml_extra/bootstrap_ci.py --dataset data/processed/<run>/dataset.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import f1_score

import common

ART = Path(__file__).resolve().parent / "artifacts"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--n", type=int, default=2000, help="nº de remuestreos")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    X_tr, X_te, y_tr, y_te, le, scaler = common.load_and_split(args.dataset)
    rng = np.random.default_rng(args.seed)
    out = {}
    for name in ("rf", "xgb"):
        path = ART / f"{name}.joblib"
        if not path.exists():
            continue
        model = joblib.load(path)
        y_pred = model.predict(X_te)
        point = f1_score(y_te, y_pred, average="macro", zero_division=0)
        n = len(y_te)
        boots = np.empty(args.n)
        for i in range(args.n):
            idx = rng.integers(0, n, n)
            boots[i] = f1_score(y_te[idx], y_pred[idx], average="macro", zero_division=0)
        lo, hi = np.percentile(boots, [2.5, 97.5])
        out[name] = {
            "f1_macro_point": float(point),
            "f1_macro_mean": float(boots.mean()),
            "ci95_low": float(lo),
            "ci95_high": float(hi),
            "n_test": int(n),
            "n_boot": args.n,
        }
        print(f"{name}: F1-macro {point:.3f}  IC95% [{lo:.3f}, {hi:.3f}]  (n_test={n})")

    (ART / "bootstrap_ci.json").write_text(json.dumps(out, indent=2))
    print("→", ART / "bootstrap_ci.json")


if __name__ == "__main__":
    main()
