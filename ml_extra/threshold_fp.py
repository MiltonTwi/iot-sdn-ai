#!/usr/bin/env python3
"""Afinado de umbral para la detección binaria (ATTACK vs BENIGN).

El FPR benigno alto (~18 %) sale de usar argmax por defecto. Aquí barremos el
umbral sobre P(ATTACK) del clasificador multiclase (colapsado a binario) en el
hold-out fold-0 y reportamos la curva precision/recall/FPR, más el punto de
operación que mantiene FPR benigno ≤ objetivo (default 5 %).

  python ml_extra/threshold_fp.py --dataset data/processed/<run>/dataset.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np

import common

ART = Path(__file__).resolve().parent / "artifacts"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--model", default="rf", choices=["rf", "xgb"])
    p.add_argument("--target-fpr", type=float, default=0.05)
    args = p.parse_args()

    X_tr, X_te, y_tr, y_te, le, scaler = common.load_and_split(args.dataset)
    model = joblib.load(ART / f"{args.model}.joblib")
    classes = list(le.classes_)
    benign_idx = classes.index("BENIGN")

    proba = model.predict_proba(X_te)
    p_attack = 1.0 - proba[:, benign_idx]
    is_attack_true = (y_te != benign_idx).astype(int)

    n_benign = int((is_attack_true == 0).sum())
    n_attack = int((is_attack_true == 1).sum())

    rows = []
    for thr in np.linspace(0.05, 0.99, 19):
        pred = (p_attack >= thr).astype(int)
        tp = int(((pred == 1) & (is_attack_true == 1)).sum())
        fp = int(((pred == 1) & (is_attack_true == 0)).sum())
        fn = int(((pred == 0) & (is_attack_true == 1)).sum())
        recall = tp / n_attack if n_attack else 0.0
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        fpr = fp / n_benign if n_benign else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        rows.append({"thr": round(float(thr), 3), "recall": recall,
                     "precision": precision, "fpr_benign": fpr, "f1": f1})

    # punto de operación: menor umbral con FPR ≤ objetivo (maximiza recall)
    ok = [r for r in rows if r["fpr_benign"] <= args.target_fpr]
    op = min(ok, key=lambda r: r["thr"]) if ok else max(rows, key=lambda r: r["f1"])

    default = next(r for r in rows if abs(r["thr"] - 0.5) < 0.03)
    print(f"modelo={args.model}  benign={n_benign} attack={n_attack}")
    print(f"umbral 0.5 (default): recall={default['recall']:.3f} "
          f"FPR={default['fpr_benign']:.3f} F1={default['f1']:.3f}")
    print(f"operación (FPR≤{args.target_fpr}): thr={op['thr']} "
          f"recall={op['recall']:.3f} FPR={op['fpr_benign']:.3f} F1={op['f1']:.3f}")

    out = {"model": args.model, "target_fpr": args.target_fpr,
           "n_benign": n_benign, "n_attack": n_attack,
           "operating_point": op, "curve": rows}
    (ART / "threshold_fp.json").write_text(json.dumps(out, indent=2))
    print("→", ART / "threshold_fp.json")


if __name__ == "__main__":
    main()
