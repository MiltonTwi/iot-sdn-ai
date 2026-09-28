"""Random Forest multiclass."""

from __future__ import annotations

from sklearn.ensemble import RandomForestClassifier


def build():
    return RandomForestClassifier(
        n_estimators=300,
        max_depth=None,
        min_samples_leaf=1,
        min_samples_split=2,
        n_jobs=-1,
        random_state=42,
        # Sin class_weight: el balanceo sobrepondera las clases de amplificacion
        # (DNS/CoAP/SSDP, ~200-350 muestras) cuyo trafico solapa con el benigno,
        # arrastrando el recall de BENIGN a 0.24 (76% falsos positivos). Sin
        # balanceo: BENIGN recall 0.997 y F1-macro 0.78->0.82. Las amplificaciones
        # raras quedan sub-detectadas en multiclase (las cubre la capa de anomalias).
        class_weight=None,
    )
