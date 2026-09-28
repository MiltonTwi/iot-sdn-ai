#!/usr/bin/env python3
"""Evaluación honesta con CV agrupada (StratifiedGroupKFold, 5 folds).

Ninguna firma de flujo (src,dst,dport,proto) cruza train/test → sin data leakage.
Reporta F1/recall por clase promediados SOLO sobre los folds donde la clase tuvo
soporte de test, y cuenta en cuántos folds cada clase fue testeable (diagnóstico
de diversidad de datos). Escribe cv_grouped.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml_extra import common  # noqa: E402
from ml_extra.models import rf as rf_mod  # noqa: E402

from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import LabelEncoder, StandardScaler

ART = Path(__file__).resolve().parent / "artifacts"
N_SPLITS = 5


def _build(name, num_class):
    if name == "rf":
        return rf_mod.build()
    if name == "mlp":
        from ml_extra.models import mlp as mlp_mod
        return mlp_mod.build()
    from ml_extra.models import xgb as xgb_mod
    return xgb_mod.build(num_class=num_class)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--models", nargs="+", default=["rf", "xgb"], choices=["rf", "xgb", "mlp"])
    ap.add_argument("--out", type=Path, default=ART / "cv_grouped.json")
    args = ap.parse_args()

    X, y, groups = common.load_dataset(args.dataset, with_groups=True)
    le = LabelEncoder()
    y_enc = le.fit_transform(y)
    C = len(le.classes_)
    print(f"[+] {len(X)} filas, {C} clases, {len(set(groups))} grupos, {N_SPLITS}-fold grouped CV")

    sgkf = StratifiedGroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=42)
    folds = list(sgkf.split(X, y_enc, groups))

    out = {"n_splits": N_SPLITS, "classes": list(le.classes_), "models": {}}
    for name in args.models:
        f1_by_class = {c: [] for c in range(C)}
        rec_by_class = {c: [] for c in range(C)}
        testable = np.zeros(C, dtype=int)   # en cuántos folds la clase tuvo soporte
        macro_f1, acc = [], []
        t0 = time.time()
        for fi, (tr, te) in enumerate(folds):
            scaler = StandardScaler()
            Xtr = scaler.fit_transform(X.iloc[tr])
            Xte = scaler.transform(X.iloc[te])
            if name == "xgb":
                # XGB exige etiquetas contiguas 0..k-1; si un fold de train no
                # tiene todas las clases, remapear a locales y volver a global.
                uniq = np.unique(y_enc[tr])
                remap = {int(o): i for i, o in enumerate(uniq)}
                inv = {i: int(o) for o, i in remap.items()}
                ytr_local = np.array([remap[int(v)] for v in y_enc[tr]])
                m = _build(name, len(uniq))
                m.fit(Xtr, ytr_local)
                pred = np.array([inv[int(v)] for v in m.predict(Xte)])
            else:
                m = _build(name, C)
                m.fit(Xtr, y_enc[tr])
                pred = m.predict(Xte)
            supp = np.bincount(y_enc[te], minlength=C)
            f1a = f1_score(y_enc[te], pred, labels=range(C), average=None, zero_division=0)
            reca = recall_score(y_enc[te], pred, labels=range(C), average=None, zero_division=0)
            present = supp > 0
            testable += present.astype(int)
            for c in range(C):
                if present[c]:
                    f1_by_class[c].append(float(f1a[c]))
                    rec_by_class[c].append(float(reca[c]))
            macro_f1.append(float(f1a[present].mean()))  # macro solo sobre clases con soporte
            acc.append(float(accuracy_score(y_enc[te], pred)))
            print(f"  {name} fold{fi}: acc={acc[-1]:.4f} macroF1(present)={macro_f1[-1]:.4f} clases_test={int(present.sum())}")
        out["models"][name] = {
            "train_s_total": time.time() - t0,
            "accuracy_mean": float(np.mean(acc)), "accuracy_std": float(np.std(acc)),
            "macro_f1_mean": float(np.mean(macro_f1)), "macro_f1_std": float(np.std(macro_f1)),
            "per_class": {
                le.classes_[c]: {
                    "f1_mean": float(np.mean(f1_by_class[c])) if f1_by_class[c] else None,
                    "recall_mean": float(np.mean(rec_by_class[c])) if rec_by_class[c] else None,
                    "testable_folds": int(testable[c]),
                } for c in range(C)
            },
        }
        mm = out["models"][name]
        print(f"[=] {name}: acc={mm['accuracy_mean']:.4f}±{mm['accuracy_std']:.4f}  "
              f"macroF1={mm['macro_f1_mean']:.4f}±{mm['macro_f1_std']:.4f}")

    args.out.write_text(json.dumps(out, indent=2))
    print(f"[+] escrito {args.out}")

    # tabla diagnóstico de diversidad
    print("\n=== diversidad / testabilidad por clase (folds con soporte de test) ===")
    ref = out["models"][args.models[0]]["per_class"]
    for cls, d in sorted(ref.items(), key=lambda kv: kv[1]["testable_folds"]):
        f1 = d["f1_mean"]
        print(f"  {cls:<24} testable_folds={d['testable_folds']}/{N_SPLITS}  f1_mean={'n/a' if f1 is None else f'{f1:.3f}'}")


if __name__ == "__main__":
    main()
