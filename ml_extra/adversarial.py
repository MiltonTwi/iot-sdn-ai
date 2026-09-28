#!/usr/bin/env python3
"""Adversarial robustness: ruido gaussiano sobre features continuas, mide caída F1.

Correcciones vs versión previa:
  - Ruido SOLO sobre features continuas (excluye flags binarias is_*), que tras
    StandardScaler tenían magnitud grande y un ruido mínimo las flipeaba,
    exagerando la fragilidad de XGB de forma artificial.
  - Split anti-fuga (grouped, seed 42) → consistente con los modelos guardados.
  - Dataset por --dataset (sin path hardcodeado a la VM).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import f1_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml_extra import common  # noqa: E402

ART = Path(__file__).resolve().parent / "artifacts"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, required=True)
    args = ap.parse_args()

    X, y, groups = common.load_dataset(args.dataset, with_groups=True)
    cont_mask = np.array([not c.startswith("is_") for c in X.columns])  # continuas
    X_tr, X_te, y_tr, y_te, le, _ = common.split_grouped(X, y, groups)

    rng = np.random.default_rng(42)
    sigmas = [0.0, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0]
    results = {"note": "ruido solo en features continuas; split grouped (anti-fuga)"}
    fig, ax = plt.subplots(figsize=(10, 6))
    for name in ["rf", "xgb"]:
        m = joblib.load(ART / f"{name}.joblib")
        f1s = []
        for sigma in sigmas:
            noise = rng.normal(0, sigma, size=X_te.shape) * cont_mask  # 0 en binarias
            pred = m.predict(X_te + noise)
            f1 = f1_score(y_te, pred, average="macro", zero_division=0)
            f1s.append(float(f1))
            print(f"  {name}  sigma={sigma:.2f}  F1 macro={f1:.4f}")
        results[name] = {"sigmas": sigmas, "f1": f1s}
        ax.plot(sigmas, f1s, "o-", label=name.upper(), linewidth=2)

    ax.set_xlabel("sigma (ruido gaussiano sobre features CONTINUAS escaladas)")
    ax.set_ylabel("F1 macro")
    ax.set_title("Adversarial robustness — degradacion con ruido (split anti-fuga)")
    ax.legend(); ax.grid(alpha=0.3); plt.tight_layout()
    plt.savefig(ART / "adversarial_clean13.png", dpi=120)
    (ART / "adversarial_metrics.json").write_text(json.dumps(results, indent=2))
    print(f"\nSaved: {ART}/adversarial_clean13.png")


if __name__ == "__main__":
    main()
