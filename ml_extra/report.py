#!/usr/bin/env python3
"""
Reporte de evaluación → PDF con figuras + classification_report.

Salida:
  ml_extra/artifacts/report_<run>.pdf
    - Resumen del dataset (clases, balance, splits)
    - Por modelo (rf, xgb, mlp): matriz de confusión, classification_report,
      ROC multi-clase OvR, feature importance top-15
    - IsoForest / AE: precision-recall del binario benign vs anomalía

Sin pandas en runtime gráfico — solo numpy + sklearn + matplotlib.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from sklearn.metrics import (
    auc,
    classification_report,
    confusion_matrix,
    precision_recall_curve,
    roc_curve,
)

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml_extra import common  # noqa: E402

ART = Path(__file__).resolve().parent / "artifacts"


def page_title(pdf, run_id: str, n_rows: int, n_features: int, classes: list[str]) -> None:
    fig = plt.figure(figsize=(11, 8.5))
    fig.text(0.5, 0.85, "IoT-SDN-AI — Reporte de evaluación", ha="center", size=22, weight="bold")
    fig.text(0.5, 0.78, f"run: {run_id}", ha="center", size=14, color="gray")
    body = (
        f"Dataset:        {n_rows:,} flujos\n"
        f"Features:       {n_features}\n"
        f"Clases:         {len(classes)}  ({', '.join(classes[:5])}{'…' if len(classes) > 5 else ''})\n\n"
        f"Modelos:        RandomForest, XGBoost, MLP, IsolationForest, AutoEncoder\n"
        f"Estrategia:     grouped split anti-fuga (StratifiedGroupKFold fold0) 80/20, StandardScaler\n"
    )
    fig.text(0.1, 0.4, body, family="monospace", size=11, va="center")
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def page_class_balance(pdf, y, le) -> None:
    counts = np.bincount(y)
    classes = list(le.classes_)
    order = np.argsort(-counts)
    fig, ax = plt.subplots(figsize=(11, 6))
    bars = ax.bar([classes[i] for i in order], counts[order], color="steelblue")
    ax.set_title("Distribución de clases en el dataset")
    ax.set_ylabel("Flujos")
    ax.tick_params(axis="x", rotation=60)
    for b, v in zip(bars, counts[order]):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height(), str(v), ha="center", va="bottom", size=8)
    fig.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


def page_confusion(pdf, model_name: str, y_true, y_pred, classes: list[str]) -> None:
    cm = confusion_matrix(y_true, y_pred, labels=range(len(classes)))
    cm_pct = cm / cm.sum(axis=1, keepdims=True).clip(min=1)
    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(cm_pct, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(len(classes)))
    ax.set_yticks(range(len(classes)))
    ax.set_xticklabels(classes, rotation=60, ha="right")
    ax.set_yticklabels(classes)
    ax.set_xlabel("Predicción")
    ax.set_ylabel("Real")
    ax.set_title(f"Matriz de confusión — {model_name}")
    for i in range(len(classes)):
        for j in range(len(classes)):
            v = cm[i, j]
            if v == 0:
                continue
            ax.text(j, i, str(v), ha="center", va="center",
                    color="white" if cm_pct[i, j] > 0.5 else "black", size=7)
    fig.colorbar(im, ax=ax, label="% por fila")
    fig.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


def page_classification_report(pdf, model_name: str, y_true, y_pred, classes: list[str]) -> None:
    present = sorted(set(np.asarray(y_true).tolist()) | set(np.asarray(y_pred).tolist()))
    rep = classification_report(y_true, y_pred, labels=present,
                                target_names=[classes[i] for i in present], zero_division=0)
    fig = plt.figure(figsize=(11, 8.5))
    fig.text(0.5, 0.95, f"Classification report — {model_name}", ha="center", size=14, weight="bold")
    fig.text(0.05, 0.05, rep, family="monospace", size=9, va="bottom")
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def page_roc(pdf, model_name: str, model, X_te, y_te, classes: list[str]) -> None:
    if not hasattr(model, "predict_proba"):
        return
    proba = model.predict_proba(X_te)
    fig, ax = plt.subplots(figsize=(10, 8))
    for k in range(len(classes)):
        if (y_te == k).sum() == 0:
            continue
        fpr, tpr, _ = roc_curve((y_te == k).astype(int), proba[:, k])
        a = auc(fpr, tpr)
        ax.plot(fpr, tpr, lw=1, label=f"{classes[k]} (AUC={a:.3f})")
    ax.plot([0, 1], [0, 1], "k--", lw=0.5)
    ax.set_xlabel("FPR")
    ax.set_ylabel("TPR")
    ax.set_title(f"ROC OvR — {model_name}")
    ax.legend(fontsize=7, loc="lower right")
    fig.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


def page_feature_importance(pdf, model_name: str, model, feature_names: list[str]) -> None:
    if not hasattr(model, "feature_importances_"):
        return
    imp = np.array(model.feature_importances_)
    order = np.argsort(-imp)[:15]
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(range(len(order)), imp[order][::-1], color="seagreen")
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([feature_names[i] for i in order[::-1]])
    ax.set_xlabel("Importancia")
    ax.set_title(f"Top-15 features — {model_name}")
    fig.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


def page_anomaly_pr(pdf, model_name: str, model, X_te, y_te, benign_idx: int) -> None:
    fig, ax = plt.subplots(figsize=(10, 6))
    pred = model.predict(X_te)
    y_bin = (y_te == benign_idx).astype(int)
    score = pred  # 1=benign para ambos wrappers
    fpr, tpr, _ = roc_curve(y_bin, score)
    a = auc(fpr, tpr)
    ax.plot(fpr, tpr, lw=2, label=f"benign vs anomalía (AUC={a:.3f})")
    ax.plot([0, 1], [0, 1], "k--", lw=0.5)
    ax.set_xlabel("FPR (anomalías clasificadas como benign)")
    ax.set_ylabel("TPR (benigns correctos)")
    ax.set_title(f"ROC binaria — {model_name}")
    ax.legend(loc="lower right")
    fig.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--artifacts", type=Path, default=ART)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    run_id = args.dataset.parent.name
    out = args.out or args.artifacts / f"report_{run_id}.pdf"

    X, y, groups = common.load_dataset(args.dataset, with_groups=True)
    X_tr, X_te, y_tr, y_te, le, _ = common.split_grouped(X, y, groups)  # leak-free
    feature_names: list[str] = joblib.load(args.artifacts / "feature_names.joblib")
    classes = list(le.classes_)
    benign_idx = int(np.where(le.classes_ == "BENIGN")[0][0]) if "BENIGN" in le.classes_ else 0

    metrics = {}
    if (args.artifacts / "metrics.json").exists():
        metrics = json.loads((args.artifacts / "metrics.json").read_text())

    with PdfPages(out) as pdf:
        page_title(pdf, run_id, len(X), X.shape[1], classes)
        page_class_balance(pdf, y_tr, le)

        for name in ["rf", "xgb", "mlp"]:
            model_path = args.artifacts / f"{name}.joblib"
            if not model_path.exists():
                continue
            model = joblib.load(model_path)
            y_pred = model.predict(X_te)
            page_classification_report(pdf, name, y_te, y_pred, classes)
            page_confusion(pdf, name, y_te, y_pred, classes)
            page_roc(pdf, name, model, X_te, y_te, classes)
            page_feature_importance(pdf, name, model, feature_names)

        for name in ["isoforest", "autoencoder"]:
            model_path = args.artifacts / f"{name}.joblib"
            if not model_path.exists():
                continue
            model = joblib.load(model_path)
            page_anomaly_pr(pdf, name, model, X_te, y_te, benign_idx)

    print(f"Reporte: {out}")
    if metrics:
        print()
        for k, v in metrics.items():
            if k == "_meta":
                continue
            acc = v.get("accuracy", 0)
            f1 = v.get("f1_macro", v.get("attack_f1", 0))
            print(f"  {k:<14}  acc={acc:.4f}  f1={f1:.4f}")


if __name__ == "__main__":
    main()
