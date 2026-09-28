"""MLP — 3 capas densas con dropout."""

from __future__ import annotations

from sklearn.neural_network import MLPClassifier


def build():
    return MLPClassifier(
        hidden_layer_sizes=(128, 64, 32),
        activation="relu",
        solver="adam",
        alpha=1e-4,
        batch_size=256,
        learning_rate_init=1e-3,
        max_iter=80,
        early_stopping=True,
        validation_fraction=0.1,
        random_state=42,
    )
