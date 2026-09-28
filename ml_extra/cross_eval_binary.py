#!/usr/bin/env python3
"""Cross-eval binario: BENIGN vs ATTACK. Más coarse → mejor transfer."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

EXCLUDE = {"src_ip", "dst_ip", "src_port", "dst_port", "start_ts",
           "label", "attack_family", "src_zone", "dst_zone", "src_device_type"}


def load(p: Path):
    df = pd.read_csv(p, low_memory=False)
    y = (df["label"] != "BENIGN").astype(int)  # 1=ATTACK
    X = df.drop(columns=[c for c in EXCLUDE if c in df.columns]).select_dtypes(include=["number"]).fillna(0)
    return X, y


def main():
    train_p = Path("/home/ubuntu/iot_run/dataset_p1p2_clean13.csv")
    eval_p = Path("/home/ubuntu/iot_run/cic/cic_dataset_test.csv")

    print(f"Train: {train_p}")
    Xt, yt = load(train_p)
    print(f"  shape: {Xt.shape}  ATTACK rate: {yt.mean()*100:.1f}%")

    print(f"Eval:  {eval_p}")
    Xe, ye = load(eval_p)
    print(f"  shape: {Xe.shape}  ATTACK rate: {ye.mean()*100:.1f}%")

    # Common cols only
    common_cols = [c for c in Xt.columns if c in Xe.columns]
    print(f"  common feature cols: {len(common_cols)}/{Xt.shape[1]}")
    Xt = Xt[common_cols].values
    Xe = Xe[common_cols].values

    # Downsample eval
    if len(Xe) > 200_000:
        rng = np.random.default_rng(42)
        idx = rng.choice(len(Xe), size=200_000, replace=False)
        Xe = Xe[idx]
        ye = ye.iloc[idx].reset_index(drop=True) if hasattr(ye, "iloc") else ye[idx]
    print(f"  eval sample: {len(Xe)}  ATTACK rate: {ye.mean()*100:.1f}%")

    sc = StandardScaler().fit(Xt)
    Xt_s = sc.transform(Xt)
    Xe_s = sc.transform(Xe)

    print("\n=== Train RF binario (intra → cross) ===")
    rf = RandomForestClassifier(n_estimators=300, n_jobs=-1, random_state=42, class_weight="balanced")
    rf.fit(Xt_s, yt)

    # Intra-domain on train test split first (quick)
    from sklearn.model_selection import train_test_split
    Xt_tr, Xt_te, yt_tr, yt_te = train_test_split(Xt_s, yt, test_size=0.2, random_state=42, stratify=yt)
    rf_intra = RandomForestClassifier(n_estimators=300, n_jobs=-1, random_state=42, class_weight="balanced")
    rf_intra.fit(Xt_tr, yt_tr)
    pred_intra = rf_intra.predict(Xt_te)
    proba_intra = rf_intra.predict_proba(Xt_te)[:, 1]
    intra = {
        "accuracy": float(accuracy_score(yt_te, pred_intra)),
        "f1_attack": float(f1_score(yt_te, pred_intra)),
        "precision_attack": float(precision_score(yt_te, pred_intra)),
        "recall_attack": float(recall_score(yt_te, pred_intra)),
        "auc": float(roc_auc_score(yt_te, proba_intra)),
    }
    print(f"INTRA  acc={intra['accuracy']:.4f}  f1_attack={intra['f1_attack']:.4f}  AUC={intra['auc']:.4f}")

    # Cross-domain on CIC
    pred_cross = rf.predict(Xe_s)
    proba_cross = rf.predict_proba(Xe_s)[:, 1]
    cross = {
        "accuracy": float(accuracy_score(ye, pred_cross)),
        "f1_attack": float(f1_score(ye, pred_cross, zero_division=0)),
        "precision_attack": float(precision_score(ye, pred_cross, zero_division=0)),
        "recall_attack": float(recall_score(ye, pred_cross, zero_division=0)),
        "auc": float(roc_auc_score(ye, proba_cross)),
    }
    print(f"CROSS  acc={cross['accuracy']:.4f}  f1_attack={cross['f1_attack']:.4f}  AUC={cross['auc']:.4f}")

    print(f"\nDrop: f1={intra['f1_attack']-cross['f1_attack']:+.4f}  AUC={intra['auc']-cross['auc']:+.4f}")

    out = {"intra": intra, "cross": cross}
    Path("/home/ubuntu/iot-sdn-ai/ml_extra/artifacts/cross_eval_binary.json").write_text(json.dumps(out, indent=2))
    print("\nSaved cross_eval_binary.json")


if __name__ == "__main__":
    main()
