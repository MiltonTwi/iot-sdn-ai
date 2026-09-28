"""Anomaly detector — sustituido por OneClassSVM (mismo rol que AE).

Mantenemos el nombre AutoEncoderAnomaly por compatibilidad con train_all.py
y joblib previo. Internamente usa OneClassSVM (sklearn, sin deps extra).

OCSVM aprende la frontera del manifold benigno en espacio kernel RBF.
Provee mejor separabilidad que un AE MLP estrecho cuando los ataques son
distribuciones densas (ej: SYN_FLOOD uniforme).
"""

from __future__ import annotations

import numpy as np
from sklearn.svm import OneClassSVM


class AutoEncoderAnomaly:
    def __init__(self):
        # nu=0.20 fuerza boundary más estrecha (tolera 20% errors en train)
        # gamma=auto da kernel ancho controlado por n_features
        self.model = OneClassSVM(
            kernel="rbf",
            gamma="auto",
            nu=0.20,
        )
        self.threshold_: float | None = None

    def fit(self, X, y, *, benign_index: int):
        mask = (y == benign_index)
        if mask.sum() == 0:
            raise ValueError("no hay BENIGN para anomaly detector")
        Xb = X[mask]
        if len(Xb) > 4000:
            rng = np.random.default_rng(42)
            idx = rng.choice(len(Xb), size=4000, replace=False)
            Xb = Xb[idx]
        self.model.fit(Xb)
        # Threshold: 25 percentile de scores BENIGN. Más agresivo (rechaza 25%
        # de cola de BENIGN) — protege contra ataques con scores cerca del
        # cuerpo BENIGN.
        scores = self.model.decision_function(Xb)
        self.threshold_ = float(np.quantile(scores, 0.25))
        return self

    def predict(self, X):
        scores = self.model.decision_function(X)
        return (scores >= self.threshold_).astype(int)

    def anomaly_score(self, X):
        return -self.model.decision_function(X)


def build():
    return AutoEncoderAnomaly()
