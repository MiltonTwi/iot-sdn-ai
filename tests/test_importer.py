"""Tests para iot/topology/importer.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from iot.topology.importer import (
    build_config,
    detect_edges,
    import_graphml,
    import_simple_json,
)

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "iot" / "topology" / "examples"


def _zones():
    with (ROOT / "iot" / "zones.yaml").open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_import_simple_json_ring4():
    g = import_simple_json(EX / "ring4.json")
    sw_names = {n["name"] for n in g["nodes"] if n["kind"] == "switch"}
    assert sw_names == {"r1", "r2", "r3", "r4"}
    assert len(g["edges"]) == 4


def test_import_graphml_fattree():
    g = import_graphml(EX / "fattree_k4.graphml")
    sw_names = {n["name"] for n in g["nodes"]}
    assert any(n.startswith("edge") for n in sw_names)
    assert any(n.startswith("core") for n in sw_names)
    edges = detect_edges(g)
    assert all(e.startswith("edge") for e in edges), f"edges detectados: {edges}"
    assert len(edges) == 8


def test_import_ring_detects_all_as_edges():
    g = import_simple_json(EX / "ring4.json")
    edges = detect_edges(g)
    assert len(edges) == 4


def test_build_config_from_imported_ring():
    g = import_simple_json(EX / "ring4.json")
    cfg = build_config(g, _zones())
    assert sum(1 for s in cfg["switches"] if s["type"] == "edge") == 4
    expected_hosts = (
        len(_zones()["infrastructure"]["hosts"])
        + sum(len(z["devices"]) for z in _zones()["zones"])
    )
    assert len(cfg["hosts"]) == expected_hosts
