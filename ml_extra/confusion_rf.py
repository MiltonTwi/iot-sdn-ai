#!/usr/bin/env python3
"""Matriz de confusión normalizada del RF sobre el hold-out leak-free (fold 0).

  python ml_extra/confusion_rf.py --dataset data/processed/<run>/dataset.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import confusion_matrix

import common

ART = Path(__file__).resolve().parent / "artifacts"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    args = ap.parse_args()
    _, X_te, _, y_te, le, _ = common.load_and_split(args.dataset)
    pred = joblib.load(ART / "rf.joblib").predict(X_te)
    labels = np.arange(len(le.classes_))
    cm = confusion_matrix(y_te, pred, labels=labels, normalize="true")
    fig, ax = plt.subplots(figsize=(9, 8))
    im = ax.imshow(cm, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(labels, le.classes_, rotation=60, ha="right", fontsize=8)
    ax.set_yticks(labels, le.classes_, fontsize=8)
    for i in labels:
        for j in labels:
            if cm[i, j] >= 0.005:
                ax.text(j, i, f"{cm[i, j]:.2f}", ha="center", va="center", fontsize=6,
                        color="white" if cm[i, j] > 0.5 else "black")
    ax.set_xlabel("Clase predicha")
    ax.set_ylabel("Clase real")
    fig.colorbar(im, fraction=0.046)
    fig.savefig(ART / "confusion_rf.png", dpi=130, bbox_inches="tight")
    print(f"Saved: {ART}/confusion_rf.png")


if __name__ == "__main__":
    main()
