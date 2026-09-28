"""Validación estructural de iot/attacks/catalog.yaml."""

from __future__ import annotations

import importlib
from pathlib import Path

import yaml


def test_catalog_loads():
    cat = yaml.safe_load(Path("iot/attacks/catalog.yaml").read_text())
    assert "scenarios" in cat
    assert len(cat["scenarios"]) >= 14


def test_each_scenario_has_module():
    cat = yaml.safe_load(Path("iot/attacks/catalog.yaml").read_text())
    for s in cat["scenarios"]:
        mod = importlib.import_module(f"iot.attacks.scenarios.{s['id']}")
        assert hasattr(mod, "run"), f"{s['id']} sin run()"


def test_required_fields():
    cat = yaml.safe_load(Path("iot/attacks/catalog.yaml").read_text())
    for s in cat["scenarios"]:
        assert "id" in s
        assert "label" in s
        assert "family" in s
        assert "duration_s" in s


def test_unique_labels():
    cat = yaml.safe_load(Path("iot/attacks/catalog.yaml").read_text())
    labels = [s["label"] for s in cat["scenarios"]]
    assert len(labels) == len(set(labels))
