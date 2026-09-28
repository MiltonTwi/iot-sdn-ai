#!/usr/bin/env python3
"""Fase 3 — base rate realista + PR-AUC.

El test fold-0 está dominado por ataques (BENIGN capado a 50k y floods con
miles de flujos) → prevalencia de ataque ≈ 97 %, así que la precision de la
detección sale optimista. En despliegue real el tráfico benigno domina.

Doble reporte sobre el mismo hold-out leak-free (`common.load_and_split`):
- **Balanceado/observado**: PR-AUC por clase (one-vs-rest) — capacidad por clase.
- **Realista**: detección ATTACK vs BENIGN re-pesando los benignos para simular
  prevalencias de ataque del 50 %, 10 %, 1 % y 0,1 %. Recall y FPR no cambian
  con la prevalencia; precision, F1 y PR-AUC sí.

  python ml_extra/base_rate.py --dataset data/processed/<run>/dataset.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score

import common

ART = Path(__file__).resolve().parent / "artifacts"
PREVALENCES = [None, 0.5, 0.1, 0.01, 0.001]  # None = observada en el test


def _weights(is_attack: np.ndarray, prev: float | None) -> np.ndarray:
    """Pesos que llevan la prevalencia de ataque del test a `prev`."""
    w = np.ones(len(is_attack), dtype=float)
    if prev is None:
        return w
    n_att = is_attack.sum()
    n_ben = len(is_attack) - n_att
    # peso benigno tal que n_att / (n_att + n_ben*wb) = prev
    w[is_attack == 0] = n_att * (1 - prev) / (prev * n_ben)
    return w


def _at_threshold(score, is_attack, w, thr) -> dict:
    pred = score >= thr
    tp = w[pred & (is_attack == 1)].sum()
    fp = w[pred & (is_attack == 0)].sum()
    fn = w[~pred & (is_attack == 1)].sum()
    tn = w[~pred & (is_attack == 0)].sum()
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"thr": thr, "precision": float(precision), "recall": float(recall),
            "f1": float(f1), "fpr": float(fp / (fp + tn)) if (fp + tn) else 0.0,
            # alertas falsas por cada alerta verdadera (carga del analista)
            "false_per_true_alert": float(fp / tp) if tp else None}


def _recall_at_precision(score, is_attack, w, target) -> dict:
    """Máximo recall alcanzable con precision ≥ target (umbral re-afinado)."""
    prec, rec, thr = precision_recall_curve(is_attack, score, sample_weight=w)
    ok = np.where(prec[:-1] >= target)[0]
    if len(ok) == 0:
        return {"target_precision": target, "recall": 0.0, "thr": None}
    i = ok[np.argmax(rec[ok])]
    return {"target_precision": target, "recall": float(rec[i]), "thr": float(thr[i])}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--models", nargs="+", default=["rf", "xgb"])
    args = p.parse_args()

    X_tr, X_te, y_tr, y_te, le, scaler = common.load_and_split(args.dataset)
    classes = list(le.classes_)
    benign_idx = classes.index("BENIGN")
    is_attack = (y_te != benign_idx).astype(int)

    op_thr = 0.5
    thr_file = ART / "threshold_fp.json"
    if thr_file.exists():
        op_thr = json.loads(thr_file.read_text())["operating_point"]["thr"]

    out = {"dataset": str(args.dataset), "n_test": int(len(y_te)),
           "n_benign": int((is_attack == 0).sum()), "n_attack": int(is_attack.sum()),
           "observed_attack_prevalence": float(is_attack.mean()),
           "operating_thr": op_thr, "models": {}}

    for name in args.models:
        model = joblib.load(ART / f"{name}.joblib")
        proba = model.predict_proba(X_te)

        per_class = {}
        for i, c in enumerate(classes):
            yb = (y_te == i).astype(int)
            if yb.sum() == 0:
                continue
            per_class[c] = {"support": int(yb.sum()),
                            "pr_auc": float(average_precision_score(yb, proba[:, i])),
                            "base_rate": float(yb.mean())}

        score = 1.0 - proba[:, benign_idx]
        regimes = []
        for prev in PREVALENCES:
            w = _weights(is_attack, prev)
            regimes.append({
                "attack_prevalence": prev if prev is not None else float(is_attack.mean()),
                "observed": prev is None,
                "pr_auc": float(average_precision_score(is_attack, score, sample_weight=w)),
                "roc_auc": float(roc_auc_score(is_attack, score, sample_weight=w)),
                "at_0.5": _at_threshold(score, is_attack, w, 0.5),
                "at_op": _at_threshold(score, is_attack, w, op_thr),
                "recall_at_p90": _recall_at_precision(score, is_attack, w, 0.90),
            })

        macro_prauc = float(np.mean([v["pr_auc"] for v in per_class.values()]))
        out["models"][name] = {"per_class": per_class, "macro_pr_auc": macro_prauc,
                               "detection": regimes}

        print(f"\n== {name}  macro PR-AUC por clase = {macro_prauc:.3f}")
        worst = sorted(per_class.items(), key=lambda kv: kv[1]["pr_auc"])[:4]
        print("   peores:", ", ".join(f"{c} {v['pr_auc']:.3f}" for c, v in worst))
        print(f"   {'prev':>7} {'PR-AUC':>7} {'P@op':>7} {'R@op':>7} {'F1@op':>7} {'FP/TP':>7} {'R@P90':>7}")
        for r in regimes:
            a = r["at_op"]
            fpt = f"{a['false_per_true_alert']:.2f}" if a["false_per_true_alert"] is not None else "-"
            print(f"   {r['attack_prevalence']:>7.3f} {r['pr_auc']:>7.3f} {a['precision']:>7.3f} "
                  f"{a['recall']:>7.3f} {a['f1']:>7.3f} {fpt:>7} {r['recall_at_p90']['recall']:>7.3f}")

    (ART / "base_rate.json").write_text(json.dumps(out, indent=2))
    print("\n→", ART / "base_rate.json")


if __name__ == "__main__":
    main()
