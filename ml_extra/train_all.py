#!/usr/bin/env python3
"""
Entrena los 5 modelos en serie sobre data/processed/{run}/dataset.csv.

Salidas en ml-extra/artifacts/:
  - rf.joblib, xgb.joblib, mlp.joblib, isoforest.joblib, autoencoder.joblib
  - label_encoder.joblib, scaler.joblib
  - metrics.json (precision/recall/F1 por modelo)

Si XGBoost no está instalado, lo omite con aviso.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib
import numpy as np
import pandas as pd

from ml_extra import common  # noqa: E402
from ml_extra.models import autoencoder, isoforest, mlp, rf  # noqa: E402

ART = Path(__file__).resolve().parent / "artifacts"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--out", type=Path, default=ART)
    p.add_argument("--split", choices=["grouped", "stratified"], default="grouped",
                   help="grouped = anti-fuga por firma de flujo (default); "
                        "stratified = legacy aleatorio (sufre data leakage)")
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    print(f"[+] Cargando {args.dataset}  (split={args.split})")
    if args.split == "grouped":
        X, y, groups = common.load_dataset(args.dataset, with_groups=True)
        print(f"    filas={len(X)}  features={X.shape[1]}  clases={y.nunique()}  "
              f"grupos={len(set(groups))}")
        X_tr, X_te, y_tr, y_te, le, scaler = common.split_grouped(X, y, groups)
    else:
        X, y = common.load_dataset(args.dataset)
        print(f"    filas={len(X)}  features={X.shape[1]}  clases={y.nunique()}")
        X_tr, X_te, y_tr, y_te, le, scaler = common.split_scaled(X, y)
    print(f"    train={len(y_tr)}  test={len(y_te)}  split={args.split}")

    joblib.dump(le, args.out / "label_encoder.joblib")
    joblib.dump(scaler, args.out / "scaler.joblib")
    joblib.dump(list(X.columns), args.out / "feature_names.joblib")

    benign_idx = int(np.where(le.classes_ == "BENIGN")[0][0]) if "BENIGN" in le.classes_ else 0

    metrics: dict[str, dict] = {}

    # ─── Random Forest ────────────────────────────────────────────
    print("[*] Random Forest...")
    t0 = time.time()
    m = rf.build()
    m.fit(X_tr, y_tr)
    pred = m.predict(X_te)
    metrics["rf"] = {"train_s": time.time() - t0, **common.report(y_te, pred, le)}
    joblib.dump(m, args.out / "rf.joblib")

    # ─── XGBoost (opcional) ───────────────────────────────────────
    try:
        from ml_extra.models import xgb  # type: ignore
        print("[*] XGBoost...")
        t0 = time.time()
        m = xgb.build(num_class=len(le.classes_))
        # Sin sample_weight balanceado (mismo motivo que RF: evita el 76% de
        # falsos positivos en BENIGN por sobrepeso de las amplificaciones raras).
        m.fit(X_tr, y_tr)
        pred = m.predict(X_te)
        metrics["xgb"] = {"train_s": time.time() - t0, **common.report(y_te, pred, le)}
        joblib.dump(m, args.out / "xgb.joblib")
    except ImportError:
        print("    xgboost no instalado, omitido")

    # ─── MLP ──────────────────────────────────────────────────────
    # MLPClassifier no soporta class_weight ni sample_weight → oversample manual
    # de minority classes hasta min_count para evitar que el batch loss las ignore.
    def _oversample_minority(X, y, min_count=200):
        classes, counts = np.unique(y, return_counts=True)
        Xs, ys = [X], [y]
        rng = np.random.default_rng(42)
        for c, n in zip(classes, counts):
            if n < min_count:
                idx_pool = np.where(y == c)[0]
                need = min_count - n
                idx = rng.choice(idx_pool, size=need, replace=True)
                Xs.append(X[idx])
                ys.append(np.full(need, c, dtype=y.dtype))
        return np.vstack(Xs), np.concatenate(ys)

    print("[*] MLP...")
    t0 = time.time()
    X_tr_os, y_tr_os = _oversample_minority(X_tr, y_tr, min_count=200)
    print(f"    oversample: {len(X_tr)} → {len(X_tr_os)} filas")
    m = mlp.build()
    m.fit(X_tr_os, y_tr_os)
    pred = m.predict(X_te)
    metrics["mlp"] = {"train_s": time.time() - t0, **common.report(y_te, pred, le)}
    joblib.dump(m, args.out / "mlp.joblib")

    from sklearn.metrics import f1_score, recall_score, precision_score

    def _anomaly_metrics(pred, y_te_bin):
        # 0=ATTACK (positive class for detection), 1=BENIGN
        attack_pred = 1 - pred
        attack_true = 1 - y_te_bin
        return {
            "accuracy": float((pred == y_te_bin).mean()),
            "attack_recall": float(recall_score(attack_true, attack_pred, zero_division=0)),
            "attack_precision": float(precision_score(attack_true, attack_pred, zero_division=0)),
            "attack_f1": float(f1_score(attack_true, attack_pred, zero_division=0)),
        }

    # ─── Isolation Forest (anomaly) ───────────────────────────────
    print("[*] Isolation Forest (anomaly)...")
    t0 = time.time()
    m = isoforest.build()
    m.fit(X_tr, y_tr, benign_index=benign_idx)
    pred = m.predict(X_te)
    y_te_bin = (y_te == benign_idx).astype(int)
    metrics["isoforest"] = {
        "train_s": time.time() - t0,
        "type": "anomaly_binary",
        **_anomaly_metrics(pred, y_te_bin),
    }
    joblib.dump(m, args.out / "isoforest.joblib")

    # ─── AutoEncoder (anomaly) ────────────────────────────────────
    print("[*] AutoEncoder (anomaly)...")
    t0 = time.time()
    m = autoencoder.build()
    m.fit(X_tr, y_tr, benign_index=benign_idx)
    pred = m.predict(X_te)
    metrics["autoencoder"] = {
        "train_s": time.time() - t0,
        "threshold": m.threshold_,
        "type": "anomaly_binary",
        **_anomaly_metrics(pred, y_te_bin),
    }
    joblib.dump(m, args.out / "autoencoder.joblib")

    metrics["_meta"] = {"split": args.split, "dataset": str(args.dataset)}
    (args.out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print("[+] metrics.json escrito")
    print()
    for k, v in metrics.items():
        if k == "_meta":
            continue
        if v.get("type") == "anomaly_binary":
            print(f"  {k:<14} acc={v.get('accuracy', 0):.4f}  attack_f1={v.get('attack_f1', 0):.4f}  attack_recall={v.get('attack_recall', 0):.4f}  train={v.get('train_s', 0):.1f}s")
        else:
            print(f"  {k:<14} acc={v.get('accuracy', 0):.4f}  f1_macro={v.get('f1_macro', 0):.4f}  train={v.get('train_s', 0):.1f}s")


if __name__ == "__main__":
    main()
