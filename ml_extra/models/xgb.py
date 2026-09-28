"""XGBoost multiclass — softmax."""

from __future__ import annotations


def build(num_class: int):
    from xgboost import XGBClassifier

    return XGBClassifier(
        n_estimators=400,
        max_depth=8,
        learning_rate=0.1,
        objective="multi:softprob",
        num_class=num_class,
        n_jobs=-1,
        random_state=42,
        tree_method="hist",
        eval_metric="mlogloss",
    )
