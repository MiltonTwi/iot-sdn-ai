#!/usr/bin/env python3
"""Arquitectura de detección en 2 etapas, evaluada leak-free (grouped 5-fold CV).

  Etapa 1 (detección binaria): RF  BENIGN vs ATTACK.
  Etapa 2 (clasificación):     RF multiclase entrenado SOLO con flujos de ataque;
                               clasifica el TIPO de los flujos que la etapa 1 marcó
                               como ataque.

Motivación: la clasificación fina multiclase sufre por el déficit de diversidad de
varias clases, pero la DETECCIÓN binaria es robusta. Separar ambas etapas refleja
un IDS real (alarma primero, atribución después) y evita que las clases raras
arrastren la métrica de detección.

Reporta, promediado sobre folds:
  - Etapa 1: recall/precision/F1 de ATTACK + FPR sobre BENIGN.
  - Pipeline: accuracy y macro-F1 multiclase final.
  - Delta vs RF multiclase de una sola etapa (mismo fold).
Escribe artifacts/two_stage.json.
"""
from __future__ import annotations

import argparse
import json
import sys
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, required=True)
    args = ap.parse_args()

    X, y, groups = common.load_dataset(args.dataset, with_groups=True)
    le = LabelEncoder(); y_enc = le.fit_transform(y)
    C = len(le.classes_)
    benign = int(np.where(le.classes_ == "BENIGN")[0][0])
    print(f"[+] {len(X)} filas, {C} clases, {len(set(groups))} grupos, benign_id={benign}")

    sgkf = StratifiedGroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=42)
    det = {"recall": [], "precision": [], "f1": [], "fpr_benign": []}
    two = {"acc": [], "macro_f1": []}
    one = {"acc": [], "macro_f1": []}

    for fi, (tr, te) in enumerate(sgkf.split(X, y_enc, groups)):
        sc = StandardScaler()
        Xtr = sc.fit_transform(X.iloc[tr]); Xte = sc.transform(X.iloc[te])
        ytr, yte = y_enc[tr], y_enc[te]

        # ---- Etapa 1: binario ATTACK(1) vs BENIGN(0) ----
        ytr_bin = (ytr != benign).astype(int)
        yte_bin = (yte != benign).astype(int)
        s1 = rf_mod.build(); s1.fit(Xtr, ytr_bin)
        p1 = s1.predict(Xte)
        det["recall"].append(float(recall_score(yte_bin, p1, pos_label=1, zero_division=0)))
        det["precision"].append(float(precision_score(yte_bin, p1, pos_label=1, zero_division=0)))
        det["f1"].append(float(f1_score(yte_bin, p1, pos_label=1, zero_division=0)))
        # FPR sobre benign = benignos marcados como ataque / total benignos
        benign_mask = yte_bin == 0
        det["fpr_benign"].append(float((p1[benign_mask] == 1).mean()) if benign_mask.any() else 0.0)

        # ---- Etapa 2: multiclase solo-ataques ----
        atk_tr = ytr != benign
        s2 = rf_mod.build(); s2.fit(Xtr[atk_tr], ytr[atk_tr])
        # ---- Pipeline: benign si s1 dice benign; si no, tipo de s2 ----
        pipe = np.full(len(yte), benign)
        flagged = p1 == 1
        if flagged.any():
            pipe[flagged] = s2.predict(Xte[flagged])
        present = sorted(set(yte.tolist()) | set(pipe.tolist()))
        two["acc"].append(float(accuracy_score(yte, pipe)))
        two["macro_f1"].append(float(f1_score(yte, pipe, labels=present, average="macro", zero_division=0)))

        # ---- Baseline 1-etapa (RF multiclase directo) ----
        s0 = rf_mod.build(); s0.fit(Xtr, ytr); p0 = s0.predict(Xte)
        present0 = sorted(set(yte.tolist()) | set(p0.tolist()))
        one["acc"].append(float(accuracy_score(yte, p0)))
        one["macro_f1"].append(float(f1_score(yte, p0, labels=present0, average="macro", zero_division=0)))

        print(f"  fold{fi}: DET f1={det['f1'][-1]:.3f} rec={det['recall'][-1]:.3f} "
              f"fpr={det['fpr_benign'][-1]:.3f} | 2-stage macroF1={two['macro_f1'][-1]:.3f} "
              f"| 1-stage macroF1={one['macro_f1'][-1]:.3f}")

    def ms(a): return {"mean": float(np.mean(a)), "std": float(np.std(a))}
    out = {
        "detection_stage1": {k: ms(v) for k, v in det.items()},
        "pipeline_two_stage": {k: ms(v) for k, v in two.items()},
        "baseline_one_stage": {k: ms(v) for k, v in one.items()},
    }
    (ART / "two_stage.json").write_text(json.dumps(out, indent=2))
    print("\n=== RESUMEN (5-fold grouped CV) ===")
    d = out["detection_stage1"]
    print(f"Etapa-1 DETECCIÓN ATTACK: F1={d['f1']['mean']:.3f}±{d['f1']['std']:.3f}  "
          f"recall={d['recall']['mean']:.3f}  precision={d['precision']['mean']:.3f}  "
          f"FPR_benign={d['fpr_benign']['mean']:.3f}")
    print(f"Pipeline 2-etapas: acc={out['pipeline_two_stage']['acc']['mean']:.3f}  "
          f"macroF1={out['pipeline_two_stage']['macro_f1']['mean']:.3f}±{out['pipeline_two_stage']['macro_f1']['std']:.3f}")
    print(f"Baseline 1-etapa:  acc={out['baseline_one_stage']['acc']['mean']:.3f}  "
          f"macroF1={out['baseline_one_stage']['macro_f1']['mean']:.3f}±{out['baseline_one_stage']['macro_f1']['std']:.3f}")
    print(f"[+] escrito {ART/'two_stage.json'}")


if __name__ == "__main__":
    main()
