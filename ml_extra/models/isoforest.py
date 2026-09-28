"""Isolation Forest — anomaly detector binario (BENIGN vs anomalía)."""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest


class IsoForestBinary:
    """Wrapper: entrena solo con BENIGN, predice 1=BENIGN, 0=ATTACK."""

    def __init__(self):
        # contamination=0.20 declara que 20% de train son outliers — boundary
        # más estrecha. max_samples bounded reduce variabilidad por RAM.
        self.model = IsolationForest(
            n_estimators=300,
            contamination=0.20,
            max_samples=2048,
            random_state=42,
            n_jobs=-1,
        )

    def fit(self, X, y, *, benign_index: int):
        mask = (y == benign_index)
        if mask.sum() == 0:
            raise ValueError("no hay muestras BENIGN para Isolation Forest")
        self.model.fit(X[mask])
        return self

    def predict(self, X):
        # IsolationForest: 1 = inlier, -1 = outlier
        raw = self.model.predict(X)
        return np.where(raw == 1, 1, 0)


def build():
    return IsoForestBinary()
