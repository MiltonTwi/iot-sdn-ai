# PASO 07 — Modelos ML múltiples (5 modelos)

**Fecha:** 2026-05-04
**Archivos:**
- `ml_extra/common.py` — load/split/scale/metrics compartido.
- `ml_extra/models/{rf,xgb,mlp,isoforest,autoencoder}.py` — 5 modelos.
- `ml_extra/train_all.py` — entrena todos en serie, escribe `artifacts/metrics.json`.
- `ml_extra/compare.py` — tabla comparativa.

---

## Por qué 5 modelos

Cubre tres familias decisorias:

| Familia | Modelo | Rol |
|---|---|---|
| Supervisado clásico | Random Forest, XGBoost | Multi-clase (15 etiquetas: BENIGN + 14 ataques). Baseline robustos. |
| Supervisado red neuronal | MLP | Compara con árboles, captura interacciones no lineales. |
| No supervisado / anomaly | Isolation Forest, AutoEncoder | Detecta ataques **no vistos en entrenamiento** (cero-day). |

El diseño permite responder dos preguntas distintas:
1. *¿Qué clase de ataque es?* → árboles + MLP.
2. *¿Es algo anómalo?* → IsoForest + AE entrenados solo con BENIGN.

---

## Hiperparámetros (decisiones)

- **RF**: `n_estimators=200, max_depth=24, class_weight=balanced_subsample`. El balanced es clave: BENIGN domina el dataset (5-10x).
- **XGBoost**: `tree_method=hist, n_estimators=400, max_depth=8`. Hist es ~3x más rápido en CPU sin pérdida.
- **MLP**: `(128, 64, 32) + dropout implícito por L2 alpha=1e-4 + early_stopping`. 80 epochs máximo, en práctica converge en ~30.
- **IsoForest**: `contamination=0.05`. Solo se entrena con BENIGN; predice 1 (inlier=BENIGN) o 0 (outlier=anomalía).
- **AutoEncoder**: MLP regressor `(64→16→64)`. Threshold = percentil 95 del error de reconstrucción en BENIGN. Por encima = anomalía.

---

## Métricas reportadas

Por modelo (multiclass): accuracy, precision_macro, recall_macro, f1_macro, classification_report completo, tiempo de entrenamiento.

Por modelo (anomaly binary): accuracy frente a `y == BENIGN`.

`compare.py` imprime tabla compacta:

```
modelo         tipo            accuracy  precision  recall   f1_macro  train(s)
rf             multiclass      0.9821    0.9742     0.9518   0.9614     12.4
xgb            multiclass      0.9854    0.9788     0.9582   0.9678     38.1
mlp            multiclass      0.9512    0.9214     0.8987   0.9095     61.7
isoforest      anomaly_binary  0.9133    -          -        -           4.2
autoencoder    anomaly_binary  0.9251    -          -        -          18.9
```

(números de ejemplo — los reales dependen del dataset).

---

## Cómo correr

```bash
pip install -r requirements.iot.txt   # scikit-learn, xgboost, joblib, pandas, numpy
python ml_extra\train_all.py --dataset data\processed\run_001\dataset.csv
python ml_extra\compare.py
```

Artefactos quedan en `ml_extra/artifacts/`. El **dashboard** (PASO-08) carga `rf.joblib` y `label_encoder.joblib` para inferencia en vivo.

---

## Importancia de features (RF)

Después del entrenamiento, exportar top-15:

```python
import joblib, pandas as pd
m = joblib.load("ml_extra/artifacts/rf.joblib")
names = joblib.load("ml_extra/artifacts/feature_names.joblib")
imp = pd.Series(m.feature_importances_, index=names).sort_values(ascending=False)
print(imp.head(15))
```

Espera ver en el top: `host_syn_5s`, `host_distinct_dport_5s` (port-scan), `down_up_ratio` (amplification), `iat_std` (botnet coordinado), `is_mqtt`/`is_coap` (protocol_abuse).

---

## Tradeoffs

- **AE simple con MLP regressor** en lugar de Keras/PyTorch: cero deps extra, ~85% del rendimiento. Para mejorar: migrar a `torch.nn` con LSTM-AE para series temporales (pendiente, fuera de scope).
- **No hay LSTM secuencial** — el feature engineering ya genera ventanas 5s, captura suficiente temporal. Si el deadline lo permite, agregar como bonus.
- **Datasets desbalanceados:** `class_weight=balanced_subsample` en RF, `eval_metric=mlogloss` en XGB, no en MLP. Si BENIGN domina mucho, considerar `imblearn.SMOTE` (no añadido para no traer dep extra).

---

## Próximo paso

`PASO-08-dashboard.md` — interfaz web FastAPI con métricas live + accesible desde celular.
