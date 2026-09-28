#!/usr/bin/env python3
"""
SHAP explicabilidad — top features que el RF usa para clasificar.

Genera ml_extra/artifacts/shap_summary.png con el bar plot de feature
importance global (TreeExplainer + summary_plot).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml_extra import common  # noqa: E402

ART = Path(__file__).resolve().parent / "artifacts"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--model", type=Path, default=ART / "rf.joblib")
    p.add_argument("--out", type=Path, default=ART / "shap_summary.png")
    p.add_argument("--samples", type=int, default=300, help="muestras a explicar (capped por velocidad)")
    args = p.parse_args()

    import shap

    print(f"Cargando dataset y modelo...")
    X_tr, X_te, y_tr, y_te, le, _ = common.load_and_split(args.dataset)  # leak-free (grouped)
    feature_names = joblib.load(ART / "feature_names.joblib")

    model = joblib.load(args.model)
    n = min(args.samples, X_te.shape[0])
    X_sub = X_te[:n]

    print(f"SHAP TreeExplainer sobre {n} muestras...")
    explainer = shap.TreeExplainer(model)
    sv = explainer.shap_values(X_sub)

    # Para multi-class, sv es lista por clase; usamos magnitudes globales
    if isinstance(sv, list):
        # |shap| promedio por feature, sumando todas las clases
        abs_per_class = [np.abs(s).mean(axis=0) for s in sv]
        mag = np.mean(abs_per_class, axis=0)
    else:
        # nuevo API SHAP devuelve array (n_samples, n_features, n_classes)
        if sv.ndim == 3:
            mag = np.abs(sv).mean(axis=(0, 2))
        else:
            mag = np.abs(sv).mean(axis=0)

    order = np.argsort(-mag)[:20]
    plt.figure(figsize=(10, 7))
    plt.barh(range(len(order)), mag[order][::-1], color="steelblue")
    plt.yticks(range(len(order)), [feature_names[i] for i in order[::-1]])
    plt.xlabel("|SHAP value| medio (sobre todas las clases)")
    plt.title("SHAP feature importance — top 20")
    plt.tight_layout()
    plt.savefig(args.out, dpi=120)
    plt.close()
    print(f"Salida: {args.out}")
    print()
    print("Top-10 features por SHAP:")
    for i in order[:10]:
        print(f"  {feature_names[i]:<32} |shap|={mag[i]:.4f}")


if __name__ == "__main__":
    main()
