"""Carga / split / preprocesado común a los 5 modelos."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold, train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler

EXCLUDE_COLS = {
    "src_ip", "dst_ip", "src_port", "dst_port", "start_ts",
    "label", "attack_family", "src_zone", "dst_zone", "src_device_type", "episode",
}

# Columnas que definen la "firma" de un flujo. Se usan como grupo para el split
# anti-fuga: flujos con la misma firma (casi-duplicados de un mismo burst) NO
# pueden quedar repartidos entre train y test.
GROUP_COLS = ["src_ip", "dst_ip", "dst_port", "proto"]


def load_dataset(csv_path: Path, with_groups: bool = False):
    df = pd.read_csv(csv_path)
    if "label" not in df.columns:
        raise ValueError("dataset sin columna `label` — corre label_dataset.py primero")
    y = df["label"]
    X = df.drop(columns=[c for c in EXCLUDE_COLS if c in df.columns])
    X = X.select_dtypes(include=["number"]).fillna(0)
    if with_groups:
        return X, y, make_groups(df)
    return X, y


def make_groups(df: pd.DataFrame) -> np.ndarray:
    """Grupo anti-fuga por fila.

    Datasets con columna `episode` (runs multi-episodio): el grupo de un ataque
    es su episodio (burst independiente: otra fuente, otra intensidad, otro
    momento) y el benigno se agrupa por dispositivo (src_ip). Así ningún
    episodio ni dispositivo queda partido entre train y test.
    Datasets legacy: firma de flujo (GROUP_COLS).
    """
    if "episode" in df.columns:
        ep = df["episode"].fillna("").astype(str)
        benign_dev = "BENIGN|" + df["src_ip"].astype(str)
        return np.where(ep != "", ep, benign_dev)
    cols = [c for c in GROUP_COLS if c in df.columns]
    return df[cols].astype(str).agg("|".join, axis=1).to_numpy()


def split_scaled(X, y, *, test_size: float = 0.2, seed: int = 42):
    """Split estratificado aleatorio (LEGACY — sufre fuga con flujos casi-duplicados)."""
    le = LabelEncoder()
    y_enc = le.fit_transform(y)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y_enc, test_size=test_size, random_state=seed, stratify=y_enc
    )
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)
    return X_train_s, X_test_s, y_train, y_test, le, scaler


def split_grouped(X, y, groups, *, test_size: float = 0.2, seed: int = 42):
    """Split por grupo (anti-fuga). Ninguna firma de flujo cruza train/test.

    Usa StratifiedGroupKFold: conserva la distribución de clases lo mejor posible
    mientras mantiene cada grupo entero de un solo lado. Devuelve el mismo contrato
    que split_scaled para ser intercambiable.
    """
    le = LabelEncoder()
    y_enc = le.fit_transform(y)
    n_splits = max(2, round(1.0 / test_size))  # test_size=0.2 -> 5 folds -> ~20% test
    sgkf = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    train_idx, test_idx = next(sgkf.split(X, y_enc, groups))

    # Verificación dura: cero solapamiento de grupos entre train y test.
    g = np.asarray(groups)
    leaked = set(g[train_idx]) & set(g[test_idx])
    assert not leaked, f"FUGA: {len(leaked)} grupos en train y test simultáneamente"

    X_train = X.iloc[train_idx]
    X_test = X.iloc[test_idx]
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)
    return X_train_s, X_test_s, y_enc[train_idx], y_enc[test_idx], le, scaler


def load_and_split(csv_path, *, test_size: float = 0.2, seed: int = 42):
    """Atajo leak-free: carga + split por grupo. Mismo contrato que split_scaled.

    Reemplaza el patrón `load_dataset` + `split_scaled` en toda la suite de
    análisis para que calibración/confusión/SHAP/reporte se evalúen sobre el
    MISMO test hold-out (fold 0, seed 42) que vieron los modelos guardados.
    """
    X, y, groups = load_dataset(csv_path, with_groups=True)
    return split_grouped(X, y, groups, test_size=test_size, seed=seed)


def report(y_true, y_pred, le) -> dict:
    from sklearn.metrics import (
        accuracy_score,
        classification_report,
        f1_score,
        precision_score,
        recall_score,
    )

    # Con split por grupo, una clase con muy pocas firmas puede quedar entera en
    # train (0 soporte en test). Reportamos solo las clases presentes en
    # test/predicción y listamos aparte las no testeables — el macro NO penaliza
    # clases sin soporte (no las medimos, no las suspendemos).
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    present = sorted(set(y_true.tolist()) | set(y_pred.tolist()))
    names = [le.classes_[i] for i in present]
    untested = [le.classes_[i] for i in range(len(le.classes_)) if i not in set(y_true.tolist())]

    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_macro": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "report": classification_report(y_true, y_pred, labels=present, target_names=names, zero_division=0),
        "untested_classes": untested,
    }
