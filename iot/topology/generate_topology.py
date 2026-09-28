#!/usr/bin/env python3
"""
Genera infra/configs/network_config.iot.yaml a partir de iot/zones.yaml.

Topología resultante:
  - 2 spine switches  (s_spine_1, s_spine_2)
  - 1 leaf por zona   (s_iot_{zone_id}) + 1 leaf infra (s_iot_0)
  - cada host conectado a su leaf, full-mesh spine<->leaf
  - subred y gateway por zona vienen del YAML

Salida consumida por iot/topology/mn_iot_topo.py.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "iot" / "zones.yaml"
DEFAULT_OUTPUT = ROOT / "iot" / "topology" / "network_config.iot.yaml"


def mac_for(zone_id: int, dev_index: int) -> str:
    return f"02:1f:7d:{zone_id:02x}:{dev_index:02x}:00"


def short_name(name: str, used: set[str], max_len: int = 9) -> str:
    """Trunca a 9 chars (Linux IFNAMSIZ=15, sufijo `-eth99` requiere 6).

    Garantiza unicidad incrementando un contador si hay colisión.
    """
    base = name.replace("_", "")[:max_len]
    candidate = base
    i = 1
    while candidate in used:
        suffix = str(i)
        candidate = base[: max_len - len(suffix)] + suffix
        i += 1
    used.add(candidate)
    return candidate


def build_config(zones_doc: dict) -> dict:
    spines = [
        {"name": "s_spine_1", "id": 1, "type": "spine"},
        {"name": "s_spine_2", "id": 2, "type": "spine"},
    ]

    leaves = [{"name": "s_iot_0", "id": 10, "type": "leaf", "zone": "infra"}]
    for zone in zones_doc["zones"]:
        leaves.append(
            {
                "name": zone["leaf_switch"],
                "id": 10 + int(zone["id"]),
                "type": "leaf",
                "zone": zone["name"],
            }
        )

    switches = spines + leaves

    links: list[dict] = []
    spine_port = {s["name"]: 1 for s in spines}
    leaf_port = {leaf["name"]: 1 for leaf in leaves}
    for spine in spines:
        for leaf in leaves:
            links.append(
                {
                    "source": spine["name"],
                    "source_port": spine_port[spine["name"]],
                    "target": leaf["name"],
                    "target_port": leaf_port[leaf["name"]],
                }
            )
            spine_port[spine["name"]] += 1
            leaf_port[leaf["name"]] += 1

    hosts: list[dict] = []
    next_host_port = {leaf["name"]: leaf_port[leaf["name"]] for leaf in leaves}
    used_names: set[str] = set()
    name_map: dict[str, str] = {}  # original → corto, para resolver dst

    infra = zones_doc["infrastructure"]
    for idx, h in enumerate(infra["hosts"], start=1):
        sn = short_name(h["name"], used_names)
        name_map[h["name"]] = sn
        hosts.append(
            {
                "name": sn,
                "original_name": h["name"],
                "ip": h["ip"],
                "mac": mac_for(0, idx),
                "default_route": f"via {infra['gateway']}",
                "connected_to": "s_iot_0",
                "port": next_host_port["s_iot_0"],
                "zone": "infra",
                "role": h["role"],
                "service_port": h.get("port"),
            }
        )
        next_host_port["s_iot_0"] += 1

    for zone in zones_doc["zones"]:
        leaf = zone["leaf_switch"]
        for idx, dev in enumerate(zone["devices"], start=1):
            sn = short_name(dev["name"], used_names)
            name_map[dev["name"]] = sn
            hosts.append(
                {
                    "name": sn,
                    "original_name": dev["name"],
                    "ip": dev["ip"],
                    "mac": mac_for(int(zone["id"]), idx),
                    "default_route": f"via {zone['gateway']}",
                    "connected_to": leaf,
                    "port": next_host_port[leaf],
                    "zone": zone["name"],
                    "device_type": dev["type"],
                    "proto": dev["proto"],
                    "dst": dev["dst"],  # mantiene nombre original para que runner.py resuelva via SERVERS dict
                    "rate_pps": dev["rate_pps"],
                    "payload": dev["payload"],
                }
            )
            next_host_port[leaf] += 1

    return {"switches": switches, "links": links, "hosts": hosts}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    with args.input.open("r", encoding="utf-8") as f:
        zones_doc = yaml.safe_load(f)

    cfg = build_config(zones_doc)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        f.write("# Auto-generado por iot/topology/generate_topology.py — no editar a mano\n")
        yaml.safe_dump(cfg, f, sort_keys=False, default_flow_style=False)

    n_sw = len(cfg["switches"])
    n_links = len(cfg["links"])
    n_hosts = len(cfg["hosts"])
    print(f"Generado: {args.output}")
    print(f"  switches={n_sw}  links={n_links}  hosts={n_hosts}")


if __name__ == "__main__":
    main()
