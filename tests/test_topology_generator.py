"""Tests para iot/topology/generate_topology.py."""

from __future__ import annotations

import ipaddress
from pathlib import Path

import yaml

from iot.topology.generate_topology import build_config

ROOT = Path(__file__).resolve().parents[1]


def _zones():
    with (ROOT / "iot" / "zones.yaml").open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_counts_match_yaml():
    zones = _zones()
    cfg = build_config(zones)
    expected_hosts = (
        len(zones["infrastructure"]["hosts"])
        + sum(len(z["devices"]) for z in zones["zones"])
    )
    assert len(cfg["hosts"]) == expected_hosts
    expected_leaves = 1 + len(zones["zones"])
    assert sum(1 for s in cfg["switches"] if s["type"] == "leaf") == expected_leaves
    assert sum(1 for s in cfg["switches"] if s["type"] == "spine") == 2


def test_unique_ips():
    cfg = build_config(_zones())
    ips = [h["ip"] for h in cfg["hosts"]]
    assert len(ips) == len(set(ips)), "IPs duplicadas en topología"


def test_unique_macs():
    cfg = build_config(_zones())
    macs = [h["mac"] for h in cfg["hosts"]]
    assert len(macs) == len(set(macs)), "MACs duplicadas"


def test_ips_match_subnets():
    zones = _zones()
    cfg = build_config(zones)
    by_zone = {z["name"]: ipaddress.IPv4Network(z["subnet"]) for z in zones["zones"]}
    by_zone["infra"] = ipaddress.IPv4Network(zones["infrastructure"]["subnet"])
    for h in cfg["hosts"]:
        net = by_zone[h["zone"]]
        assert ipaddress.IPv4Address(h["ip"]) in net, f"{h['name']} {h['ip']} fuera de {net}"


def test_full_mesh_links():
    cfg = build_config(_zones())
    spines = {s["name"] for s in cfg["switches"] if s["type"] == "spine"}
    leaves = {s["name"] for s in cfg["switches"] if s["type"] == "leaf"}
    assert len(cfg["links"]) == len(spines) * len(leaves)


def test_ports_unique_per_switch():
    cfg = build_config(_zones())
    seen: dict[str, set[int]] = {}
    for link in cfg["links"]:
        for sw, port in [(link["source"], link["source_port"]), (link["target"], link["target_port"])]:
            seen.setdefault(sw, set())
            assert port not in seen[sw], f"puerto {port} duplicado en {sw}"
            seen[sw].add(port)
    for h in cfg["hosts"]:
        sw, port = h["connected_to"], h["port"]
        seen.setdefault(sw, set())
        assert port not in seen[sw], f"puerto {port} duplicado en {sw} (host)"
        seen[sw].add(port)
