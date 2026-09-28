#!/usr/bin/env python3
"""Calibration analysis sobre dataset limpio (BENIGN vs anomaly binario)."""
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
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss, log_loss

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml_extra import common  # noqa: E402

DS = Path("/home/ubuntu/iot_run/dataset_p1p2_clean13.csv")
ART = Path(__file__).resolve().parent / "artifacts"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, required=True)
    args = ap.parse_args()
    X_tr, X_te, y_tr, y_te, le, _ = common.load_and_split(args.dataset)  # leak-free (grouped)
    benign_idx = int(np.where(le.classes_ == "BENIGN")[0][0])
    y_bin = (y_te == benign_idx).astype(int)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    results = {}
    for ax_i, name in enumerate(["rf", "xgb"]):
        m = joblib.load(ART / f"{name}.joblib")
        proba = m.predict_proba(X_te)
        p_benign = proba[:, benign_idx]
        frac_pos, mean_pred = calibration_curve(y_bin, p_benign, n_bins=10, strategy="quantile")
        brier = brier_score_loss(y_bin, p_benign)
        ll = log_loss(y_bin, np.clip(p_benign, 1e-7, 1 - 1e-7))
        print(f"{name}: brier={brier:.4f}  log_loss={ll:.4f}")
        results[name] = {"brier": float(brier), "log_loss": float(ll)}
        ax = axes[ax_i]
        ax.plot([0, 1], [0, 1], "k--", alpha=0.5, label="Perfecta")
        ax.plot(mean_pred, frac_pos, "o-", label=f"{name.upper()} Brier={brier:.3f}")
        ax.set_xlabel("Probabilidad media predicha (BENIGN)")
        ax.set_ylabel("Fracción real BENIGN")
        ax.set_title(f"Calibración — {name.upper()}")
        ax.legend()
        ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(ART / "calibration_clean13.png", dpi=120)
    (ART / "calibration_metrics.json").write_text(json.dumps(results, indent=2))
    print(f"Saved: {ART}/calibration_clean13.png")


if __name__ == "__main__":
    main()
