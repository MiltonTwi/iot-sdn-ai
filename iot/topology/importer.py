#!/usr/bin/env python3
"""
Importador automático de topologías → network_config.iot.yaml.

Formatos soportados (--from):
  graphml       Internet Topology Zoo, NetworkX export, etc.
  nx-json       NetworkX node-link JSON
  mininet-py    Script Mininet .py (parseo AST: addSwitch/addHost/addLink)
  ryu-api       Descubrimiento en vivo via http://controller:8080/v1.0/topology
  json          Formato propio simple {"switches": [...], "links": [...]}

Estrategia de poblado IoT:
  Identifica nodos "edge" (degree 1 en el grafo de switches, o explícitos por
  atributo) y distribuye las zonas declaradas en iot/zones.yaml entre ellos.
  Cada zona aterriza en UN edge → todos sus dispositivos cuelgan de ese leaf.
  Si zonas > edges, las extras se asignan round-robin a los mismos edges.
  Si edges > zonas, los edges sobrantes quedan sin IoT (solo transit).

Uso:
  python -m iot.topology.importer \
    --from graphml --input red.graphml \
    --zones iot/zones.yaml \
    --out iot/topology/network_config.iot.yaml
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


# ─────────────────────────────────────────────────────────────────
#  Representación interna
# ─────────────────────────────────────────────────────────────────
#  graph = {
#    "nodes":  [{"name": str, "kind": "switch"|"host", "attrs": {...}}],
#    "edges":  [{"source": str, "target": str, "attrs": {...}}],
#  }
# ─────────────────────────────────────────────────────────────────


def import_graphml(path: Path) -> dict:
    ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
    tree = ET.parse(path)
    root = tree.getroot()
    # mapa key-id → (for-node|for-edge, attr.name)
    keys: dict[str, tuple[str, str]] = {}
    for k in root.findall("g:key", ns):
        keys[k.attrib["id"]] = (k.attrib.get("for", ""), k.attrib.get("attr.name", k.attrib.get("id")))

    g = root.find("g:graph", ns)
    if g is None:
        raise ValueError("graphml sin <graph>")

    nodes: list[dict] = []
    for n in g.findall("g:node", ns):
        attrs: dict = {}
        for d in n.findall("g:data", ns):
            kn = keys.get(d.attrib["key"], ("", d.attrib["key"]))[1]
            attrs[kn] = d.text
        nodes.append({
            "name": _slug(n.attrib["id"]),
            "kind": "switch",
            "attrs": attrs,
        })

    edges: list[dict] = []
    for e in g.findall("g:edge", ns):
        edges.append({
            "source": _slug(e.attrib["source"]),
            "target": _slug(e.attrib["target"]),
            "attrs": {},
        })
    return {"nodes": nodes, "edges": edges}


def import_nx_json(path: Path) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    nodes_in = doc.get("nodes", [])
    links_in = doc.get("links", doc.get("edges", []))
    id_key = "id"
    nodes: list[dict] = []
    for n in nodes_in:
        nid = str(n.get(id_key, n.get("name", n.get("label", ""))))
        nodes.append({"name": _slug(nid), "kind": "switch", "attrs": {k: v for k, v in n.items() if k != id_key}})
    edges: list[dict] = []
    for l in links_in:
        s = str(l.get("source"))
        t = str(l.get("target"))
        # NetworkX exporta a veces con índices numéricos referenciando nodes[i]
        if s.isdigit() and int(s) < len(nodes_in):
            s = str(nodes_in[int(s)].get(id_key, s))
        if t.isdigit() and int(t) < len(nodes_in):
            t = str(nodes_in[int(t)].get(id_key, t))
        edges.append({"source": _slug(s), "target": _slug(t), "attrs": {}})
    return {"nodes": nodes, "edges": edges}


def import_mininet_py(path: Path) -> dict:
    """Parseo AST de scripts Mininet. Captura llamadas:
        net.addSwitch('s1') | self.addSwitch('s1')
        net.addHost('h1')   | self.addHost('h1')
        net.addLink(a, b)   | self.addLink(a, b)
    """
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_names: set[str] = set()

    def name_of(arg) -> str | None:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
        if isinstance(arg, ast.Name):
            return arg.id
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        attr = node.func.attr if isinstance(node.func, ast.Attribute) else None
        if attr not in {"addSwitch", "addHost", "addLink"}:
            continue
        if attr == "addSwitch" and node.args:
            n = name_of(node.args[0])
            if n and n not in seen_names:
                nodes.append({"name": _slug(n), "kind": "switch", "attrs": {}})
                seen_names.add(n)
        elif attr == "addHost" and node.args:
            n = name_of(node.args[0])
            if n and n not in seen_names:
                nodes.append({"name": _slug(n), "kind": "host", "attrs": {}})
                seen_names.add(n)
        elif attr == "addLink" and len(node.args) >= 2:
            s, t = name_of(node.args[0]), name_of(node.args[1])
            if s and t:
                edges.append({"source": _slug(s), "target": _slug(t), "attrs": {}})
    if not nodes:
        raise ValueError("no detecté addSwitch/addHost en el script — patrón no reconocido")
    return {"nodes": nodes, "edges": edges}


def import_ryu_api(base_url: str) -> dict:
    sw = json.loads(urllib.request.urlopen(f"{base_url}/v1.0/topology/switches", timeout=5).read())
    lk = json.loads(urllib.request.urlopen(f"{base_url}/v1.0/topology/links", timeout=5).read())
    nodes = [{"name": f"s{int(s['dpid'], 16)}", "kind": "switch", "attrs": {"dpid": s["dpid"]}} for s in sw]
    edges = []
    for l in lk:
        a = f"s{int(l['src']['dpid'], 16)}"
        b = f"s{int(l['dst']['dpid'], 16)}"
        edges.append({"source": a, "target": b, "attrs": {}})
    return {"nodes": nodes, "edges": edges}


def import_simple_json(path: Path) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    nodes = []
    for s in doc.get("switches", []):
        nodes.append({"name": _slug(s["name"]), "kind": "switch", "attrs": s})
    for h in doc.get("hosts", []):
        nodes.append({"name": _slug(h["name"]), "kind": "host", "attrs": h})
    edges = [{"source": _slug(l["source"]), "target": _slug(l["target"]), "attrs": l} for l in doc.get("links", [])]
    return {"nodes": nodes, "edges": edges}


# ─────────────────────────────────────────────────────────────────
#  Edge detection + zona binding
# ─────────────────────────────────────────────────────────────────

def detect_edges(graph: dict, *, hint_attr: str = "type") -> list[str]:
    """Devuelve lista de switches edge.

    Estrategia:
      1) Si algún nodo tiene attrs[hint_attr] in {edge,leaf,access,tor}, usa esos.
      2) Si no, calcula degree y elige los de degree mínimo (excluyendo aislados).
    """
    switches = [n for n in graph["nodes"] if n["kind"] == "switch"]
    by_name = {n["name"]: n for n in switches}

    explicit = [
        n["name"] for n in switches
        if str(n["attrs"].get(hint_attr, "")).lower() in {"edge", "leaf", "access", "tor"}
    ]
    if explicit:
        return explicit

    deg: dict[str, int] = defaultdict(int)
    for e in graph["edges"]:
        if e["source"] in by_name:
            deg[e["source"]] += 1
        if e["target"] in by_name:
            deg[e["target"]] += 1
    if not deg:
        return [n["name"] for n in switches]

    min_deg = min(deg.values())
    edges = [name for name, d in deg.items() if d == min_deg]
    # si todos tienen mismo degree (mesh / ring), todos son edges
    return edges


def assign_ports(graph: dict) -> tuple[list[dict], list[dict]]:
    """Convierte edges genéricos en links con (source_port, target_port) consecutivos."""
    sw_links: list[dict] = []
    port_counter: dict[str, int] = defaultdict(lambda: 1)
    sw_names = {n["name"] for n in graph["nodes"] if n["kind"] == "switch"}

    for e in graph["edges"]:
        s, t = e["source"], e["target"]
        if s not in sw_names or t not in sw_names:
            continue  # ignora links host (asignados luego)
        sp = port_counter[s]; port_counter[s] += 1
        tp = port_counter[t]; port_counter[t] += 1
        sw_links.append({"source": s, "source_port": sp, "target": t, "target_port": tp})

    return sw_links, [],


def build_config(
    graph: dict,
    zones_doc: dict,
    *,
    ip_prefix: str = "10.10",
    gateway_suffix: int = 254,
    mac_oui: str = "02:1f:7d",
) -> dict:
    sw_nodes = [n for n in graph["nodes"] if n["kind"] == "switch"]
    edges_list = detect_edges(graph)
    if not edges_list:
        raise ValueError("no se detectaron switches edge")

    switches_out: list[dict] = []
    name_to_id: dict[str, int] = {}
    for i, n in enumerate(sw_nodes, start=1):
        name_to_id[n["name"]] = i
        kind = "edge" if n["name"] in edges_list else "core"
        switches_out.append({"name": n["name"], "id": i, "type": kind})

    # links inter-switch con port asignado
    port_counter: dict[str, int] = defaultdict(lambda: 1)
    links_out: list[dict] = []
    sw_set = {n["name"] for n in sw_nodes}
    for e in graph["edges"]:
        s, t = e["source"], e["target"]
        if s not in sw_set or t not in sw_set:
            continue
        sp = port_counter[s]; port_counter[s] += 1
        tp = port_counter[t]; port_counter[t] += 1
        links_out.append({"source": s, "source_port": sp, "target": t, "target_port": tp})

    # ── Distribución de zonas sobre edges ──────────────────────
    zones = zones_doc["zones"]
    infra = zones_doc["infrastructure"]

    # primer edge = zona infra (servidores). Resto, round-robin sobre el resto.
    leaf_for_infra = edges_list[0]
    pool = edges_list[1:] or edges_list
    leaf_for_zone: dict[int, str] = {}
    for i, z in enumerate(zones):
        leaf_for_zone[z["id"]] = pool[i % len(pool)]

    # ── Hosts ─────────────────────────────────────────────────
    hosts_out: list[dict] = []

    def add_host(name, ip, mac, route, leaf, zone, **extra):
        hosts_out.append({
            "name": _slug(name),
            "ip": ip,
            "mac": mac,
            "default_route": route,
            "connected_to": leaf,
            "port": port_counter[leaf],
            "zone": zone,
            **extra,
        })
        port_counter[leaf] += 1

    # infra (zona 0)
    for idx, h in enumerate(infra["hosts"], start=1):
        add_host(
            name=h["name"], ip=h["ip"],
            mac=_mac(mac_oui, 0, idx),
            route=f"via {infra['gateway']}",
            leaf=leaf_for_infra, zone="infra",
            role=h["role"], service_port=h.get("port"),
        )

    # zonas
    for z in zones:
        leaf = leaf_for_zone[z["id"]]
        # re-IP automático si la subnet no encaja con prefix
        zone_subnet = f"{ip_prefix}.{z['id']}.0/24"
        zone_gw = f"{ip_prefix}.{z['id']}.{gateway_suffix}"
        for idx, dev in enumerate(z["devices"], start=1):
            ip = f"{ip_prefix}.{z['id']}.{idx + 9}"  # .10, .11, ...
            add_host(
                name=dev["name"], ip=ip,
                mac=_mac(mac_oui, int(z["id"]), idx),
                route=f"via {zone_gw}",
                leaf=leaf, zone=z["name"],
                device_type=dev["type"], proto=dev["proto"],
                dst=dev["dst"], rate_pps=dev["rate_pps"], payload=dev["payload"],
            )

    return {"switches": switches_out, "links": links_out, "hosts": hosts_out}


# ─────────────────────────────────────────────────────────────────
#  helpers
# ─────────────────────────────────────────────────────────────────

def _slug(s: str) -> str:
    out = "".join(c if c.isalnum() else "_" for c in str(s))
    if out and out[0].isdigit():
        out = "n_" + out
    return out


def _mac(oui: str, zone: int, idx: int) -> str:
    return f"{oui}:{zone:02x}:{idx:02x}:00"


# ─────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────

IMPORTERS = {
    "graphml":    import_graphml,
    "nx-json":    import_nx_json,
    "mininet-py": import_mininet_py,
    "json":       import_simple_json,
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="src", required=True,
                   choices=list(IMPORTERS) + ["ryu-api"])
    p.add_argument("--input", help="ruta al archivo (o URL base ryu-api)", required=True)
    p.add_argument("--zones", type=Path, default=ROOT / "iot" / "zones.yaml")
    p.add_argument("--out", type=Path, default=ROOT / "iot" / "topology" / "network_config.iot.yaml")
    p.add_argument("--ip-prefix", default="10.10")
    p.add_argument("--mac-oui", default="02:1f:7d")
    args = p.parse_args()

    if args.src == "ryu-api":
        graph = import_ryu_api(args.input)
    else:
        graph = IMPORTERS[args.src](Path(args.input))

    with args.zones.open("r", encoding="utf-8") as f:
        zones_doc = yaml.safe_load(f)

    cfg = build_config(graph, zones_doc, ip_prefix=args.ip_prefix, mac_oui=args.mac_oui)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        f.write(f"# Auto-generado por importer (--from {args.src} {args.input}) — no editar a mano\n")
        yaml.safe_dump(cfg, f, sort_keys=False, default_flow_style=False)

    n_sw = len(cfg["switches"])
    n_links = len(cfg["links"])
    n_hosts = len(cfg["hosts"])
    edge_count = sum(1 for s in cfg["switches"] if s["type"] == "edge")
    print(f"Importado:")
    print(f"  fuente   : {args.src} ({args.input})")
    print(f"  switches : {n_sw}  (edge={edge_count} core={n_sw - edge_count})")
    print(f"  links    : {n_links}")
    print(f"  hosts    : {n_hosts}")
    print(f"  salida   : {args.out}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[!] {e}", file=sys.stderr)
        sys.exit(1)
