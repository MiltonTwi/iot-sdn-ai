#!/usr/bin/env python3
"""
Cross-evaluación: entrena en dataset A, evalúa en dataset B.

Caso típico:
  --train data/processed/run_synth/dataset.csv     (lab sintético)
  --eval  data/processed/cic_iot_2023/dataset.csv  (público)

Reporta:
  - accuracy/F1 en train (split interno)
  - accuracy/F1 en eval (cross-domain)
  - drop relativo

Saca tabla compacta para defensa.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import joblib
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml_extra import common  # noqa: E402
from ml_extra.models import rf  # noqa: E402

ART = Path(__file__).resolve().parent / "artifacts"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--train", type=Path, required=True)
    p.add_argument("--eval", type=Path, required=True)
    p.add_argument("--out", type=Path, default=ART / "cross_eval.json")
    p.add_argument("--shared-features", action="store_true",
                   help="entrena y evalua SOLO con features que ambos dominios proveen "
                        "(excluye host_*/dst_*, que CIC no reconstruye). Mide shift de "
                        "dominio REAL en vez de disponibilidad de features.")
    args = p.parse_args()

    print(f"[+] Train sobre {args.train}")
    Xa, ya, ga = common.load_dataset(args.train, with_groups=True)
    if args.shared_features:
        # CIC da 1 fila por flujo: no reconstruye ventanas host_*/dst_*. Si se
        # entrena con ellas (top-features del modelo lab) y en CIC valen 0, el
        # "drop" mide features ausentes, no dominio. Restringimos a la intersección.
        import pandas as _pd
        feat_b0 = set(_pd.read_csv(args.eval, nrows=1).columns)
        drop = {c for c in Xa.columns if c.startswith(("host_", "dst_"))}
        shared = [c for c in Xa.columns if c in feat_b0 and c not in drop]
        print(f"  [shared-features] {len(shared)}/{len(Xa.columns)} comunes: {shared}")
        Xa = Xa[shared]
    Xa_tr, Xa_te, ya_tr, ya_te, le_a, scaler = common.split_grouped(Xa, ya, ga)  # leak-free
    feat_a = list(Xa.columns)
    model = rf.build()
    model.fit(Xa_tr, ya_tr)
    rep_intra = common.report(ya_te, model.predict(Xa_te), le_a)
    print(f"  intra-domain  acc={rep_intra['accuracy']:.4f}  f1={rep_intra['f1_macro']:.4f}")

    print(f"[+] Eval sobre {args.eval}")
    Xb, yb = common.load_dataset(args.eval)
    feat_b = list(Xb.columns)

    # Alinear features (B puede tener menos columnas)
    common_feats = [f for f in feat_a if f in feat_b]
    Xb_aligned = Xb[common_feats].copy()
    for f in feat_a:
        if f not in common_feats:
            Xb_aligned[f] = 0
    Xb_aligned = Xb_aligned[feat_a]

    Xb_scaled = scaler.transform(Xb_aligned)

    # Re-encode labels (B puede tener clases que A no vio)
    yb_filtered = np.array([y if y in le_a.classes_ else "BENIGN" for y in yb])
    yb_enc = le_a.transform(yb_filtered)

    pred = model.predict(Xb_scaled)
    # Manual report (common.report falla si pred no incluye todas las clases del LE)
    from sklearn.metrics import accuracy_score, f1_score, classification_report
    acc_cross = accuracy_score(yb_enc, pred)
    f1m_cross = f1_score(yb_enc, pred, average="macro", zero_division=0)
    f1w_cross = f1_score(yb_enc, pred, average="weighted", zero_division=0)
    rep_cross = {"accuracy": float(acc_cross), "f1_macro": float(f1m_cross), "f1_weighted": float(f1w_cross)}
    print(f"  cross-domain  acc={acc_cross:.4f}  f1_macro={f1m_cross:.4f}  f1_weighted={f1w_cross:.4f}")
    eval_labels = sorted(set(yb_enc.tolist()))
    print("\nClassification report (clases presentes en eval):")
    print(classification_report(yb_enc, pred, labels=eval_labels,
                                 target_names=[le_a.classes_[i] for i in eval_labels],
                                 zero_division=0))

    drop_acc = rep_intra['accuracy'] - rep_cross['accuracy']
    drop_f1 = rep_intra['f1_macro'] - rep_cross['f1_macro']
    print(f"  drop          acc={drop_acc:+.4f}  f1={drop_f1:+.4f}")

    import json
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "train_dataset": str(args.train),
        "eval_dataset": str(args.eval),
        "intra_domain": {"accuracy": rep_intra["accuracy"], "f1_macro": rep_intra["f1_macro"]},
        "cross_domain": {"accuracy": rep_cross["accuracy"], "f1_macro": rep_cross["f1_macro"]},
        "drop": {"accuracy": drop_acc, "f1_macro": drop_f1},
        "common_features": common_feats,
        "missing_in_eval": [f for f in feat_a if f not in feat_b],
    }, indent=2))
    print(f"  → {args.out}")


if __name__ == "__main__":
    main()
