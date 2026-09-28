#!/usr/bin/env python3
"""Confusion analysis + UMAP visualization sobre dataset limpio."""
from __future__ import annotations

import sys
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import confusion_matrix

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml_extra import common  # noqa: E402

DS = Path("/home/ubuntu/iot_run/dataset_p1p2_clean13.csv")
ART = Path(__file__).resolve().parent / "artifacts"


def confusion_pairs():
    X_tr, X_te, y_tr, y_te, le, _ = common.load_and_split(DS)  # leak-free (grouped)
    classes = list(le.classes_)
    rf = joblib.load(ART / "rf.joblib")
    pred = rf.predict(X_te)
    cm = confusion_matrix(y_te, pred, labels=range(len(classes)))
    # Identify top confusion pairs (off-diagonal)
    pairs = []
    for i in range(len(classes)):
        for j in range(len(classes)):
            if i == j:
                continue
            if cm[i, j] > 0:
                pairs.append((classes[i], classes[j], int(cm[i, j]), int(cm[i].sum())))
    pairs.sort(key=lambda x: -x[2])
    print("Top 15 confusiones (real → predicho):")
    print(f"{'Real':<22} {'Predicho':<22} {'n':>5} {'% real':>7}")
    for real, pred_lbl, n, total in pairs[:15]:
        pct = 100 * n / total if total else 0
        print(f"  {real:<22} {pred_lbl:<22} {n:>5} {pct:>6.1f}%")


def umap_plot():
    try:
        import umap
    except ImportError:
        print("umap-learn no instalado, skipping UMAP")
        return
    X_tr, X_te, y_tr, y_te, le, _ = common.load_and_split(DS)  # leak-free (grouped)
    classes = list(le.classes_)

    # Subsample por clase para que UMAP sea rápido y balanceado visual
    rng = np.random.default_rng(42)
    idxs = []
    for c in range(len(classes)):
        cls_idx = np.where(y_te == c)[0]
        n = min(200, len(cls_idx))
        if n > 0:
            idxs.extend(rng.choice(cls_idx, size=n, replace=False))
    idxs = np.array(idxs)

    print(f"UMAP sobre {len(idxs)} muestras...")
    reducer = umap.UMAP(n_neighbors=15, min_dist=0.1, random_state=42)
    emb = reducer.fit_transform(X_te[idxs])
    y_sub = y_te[idxs]

    fig, ax = plt.subplots(figsize=(12, 9))
    cmap = plt.get_cmap("tab20")
    for c in range(len(classes)):
        m = y_sub == c
        if m.sum() == 0:
            continue
        ax.scatter(emb[m, 0], emb[m, 1], s=18, alpha=0.6, label=classes[c], color=cmap(c / len(classes)))
    ax.set_title("UMAP feature space — clusters por clase")
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)
    ax.set_xlabel("UMAP-1")
    ax.set_ylabel("UMAP-2")
    plt.tight_layout()
    plt.savefig(ART / "umap_clean13.png", dpi=120, bbox_inches="tight")
    print(f"Saved: {ART}/umap_clean13.png")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, required=True)
    _args = ap.parse_args()
    DS = _args.dataset  # override global usado por confusion_pairs/umap_plot
    confusion_pairs()
    print()
    umap_plot()
