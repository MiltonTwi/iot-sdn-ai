#!/usr/bin/env python3
"""
Etiqueta el CSV de flujos cruzando contra los manifests de ataques
(/tmp/attack_*.json producidos por iot/attacks/runner.py).

Reglas:
  - Si el flow.start_ts cae dentro de [manifest.started_at, manifest.finished_at]
    Y la IP atacante es origen o destino → label = manifest.label
  - Caso contrario → label = "BENIGN"

Añade columnas: label, attack_family, src_zone, dst_zone, src_device_type.
La metadata de zona/dispositivo se cruza contra iot/zones.yaml.
"""

from __future__ import annotations

import argparse
import csv
import ipaddress
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_zones() -> dict[str, dict]:
    with (ROOT / "iot" / "zones.yaml").open("r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    by_ip: dict[str, dict] = {}
    for h in doc["infrastructure"]["hosts"]:
        by_ip[h["ip"]] = {"zone": "infra", "device_type": h["role"]}
    for z in doc["zones"]:
        for d in z["devices"]:
            by_ip[d["ip"]] = {"zone": z["name"], "device_type": d["type"]}
    return by_ip


def load_manifests(folder: Path) -> list[dict]:
    out: list[dict] = []
    for p in folder.glob("attack_*.json"):
        try:
            out.append(json.loads(p.read_text()))
        except Exception:
            continue
    return out


def attacker_ip_for(manifest: dict) -> str | None:
    # runner.py registra la IP real del namespace lanzador (episodios rotan la
    # fuente entre attacker y dispositivos IoT comprometidos).
    if manifest.get("src_ip"):
        return manifest["src_ip"]
    cfg = manifest.get("config", {})
    if cfg.get("attacker") == "attacker":
        return "10.10.0.99"  # manifests legacy sin src_ip
    return None


# Escenarios con source IP spoofeada: la fuente real no aparece en los flujos,
# se etiqueta por (target_ip, target_port, proto).
SPOOFED = {"SYN_FLOOD", "ICMP_FLOOD", "MIRAI_COORDINATED"}


def _side_matches(row: dict, ip: str, port) -> bool:
    for r_ip, r_port in ((row["src_ip"], row["src_port"]), (row["dst_ip"], row["dst_port"])):
        if r_ip == ip and (port is None or int(r_port or 0) == int(port)):
            return True
    return False


def target_match(row: dict, cfg: dict, atk_ip: str | None) -> bool:
    """El extremo NO atacante del flujo es un objetivo declarado del escenario."""
    if cfg.get("target_ip"):
        return _side_matches(row, cfg["target_ip"], cfg.get("target_port"))
    nets = cfg.get("targets_subnets") or ([cfg["targets_subnet"]] if cfg.get("targets_subnet") else [])
    if nets:
        other = row["dst_ip"] if row["src_ip"] == atk_ip else row["src_ip"]
        addr = ipaddress.ip_address(other)
        return any(addr in ipaddress.ip_network(n, strict=False) for n in nets)
    return True  # sin objetivo declarado (p.ej. arp_spoof): basta la fuente


# Amplificación: el escenario rocía el /24 de victim_ip con sport en
# [base, base+src_ports) (ver BASE_SPORT en scenarios/*_amplification.py).
# Matchear solo victim_ip dejaba ~253/254 flujos reflejados como BENIGN.
AMP_BASE_SPORT = {
    "DNS_AMPLIFICATION": 30000,
    "COAP_AMPLIFICATION": 40000,
    "SSDP_AMPLIFICATION": 50000,
}


def is_amp_flow(row: dict, label: str, cfg: dict) -> bool:
    refl_ip, refl_port = cfg.get("reflector_ip"), int(cfg.get("reflector_port", 0))
    base = int(cfg.get("base_sport", AMP_BASE_SPORT[label]))
    n_sports = int(cfg.get("src_ports", 64))
    net = ipaddress.ip_network(f"{cfg['victim_ip']}/24", strict=False)
    for a_ip, a_port, b_ip, b_port in (
        (row["src_ip"], row["src_port"], row["dst_ip"], row["dst_port"]),
        (row["dst_ip"], row["dst_port"], row["src_ip"], row["src_port"]),
    ):
        # a = víctima spoofeada, b = reflector (flujo bidireccional en cualquier sentido)
        if b_ip != refl_ip or int(b_port or 0) != refl_port:
            continue
        if ipaddress.ip_address(a_ip) in net and base <= int(a_port or 0) < base + n_sports:
            return True
    return False


def label_row(row: dict, manifests: list[dict], by_ip: dict) -> dict:
    ts = float(row["start_ts"])
    src = row["src_ip"]
    dst = row["dst_ip"]
    label = "BENIGN"
    family = "benign"
    episode = ""
    proto = int(row.get("proto", 0))
    # Cada flood/scan tiene un proto característico — usar para evitar que
    # tráfico TCP de fondo durante una ventana de ICMP_FLOOD sea mislabeled.
    PROTO_BY_LABEL = {
        "SYN_FLOOD": 6,
        "ICMP_FLOOD": 1,
        "UDP_FLOOD": 17,
        "DNS_AMPLIFICATION": 17,
        "COAP_AMPLIFICATION": 17,
        "SSDP_AMPLIFICATION": 17,
    }
    for m in manifests:
        if not (m["started_at"] <= ts <= m["finished_at"]):
            continue
        cfg = m["config"]
        # Reject por proto si el ataque tiene proto fijo
        required_proto = PROTO_BY_LABEL.get(m["label"])
        if required_proto is not None and proto != required_proto:
            continue
        if m["label"] in AMP_BASE_SPORT:
            hit = is_amp_flow(row, m["label"], cfg)
        elif m["label"] in SPOOFED:
            hit = target_match(row, cfg, None)
        else:
            # fuente real + objetivo: evita marcar como ataque el tráfico benigno
            # del dispositivo comprometido o de terceros hacia el mismo server
            atk_ip = attacker_ip_for(m)
            hit = atk_ip in (src, dst) and target_match(row, cfg, atk_ip)
        if not hit:
            continue
        label = m["label"]
        family = m["family"]
        episode = m.get("episode") or f"{m['scenario']}#0"
        break
    src_meta = by_ip.get(src, {})
    return {
        **row,
        "label": label,
        "attack_family": family,
        "episode": episode,
        "src_zone": src_meta.get("zone", "external"),
        "dst_zone": by_ip.get(dst, {}).get("zone", "external"),
        "src_device_type": src_meta.get("device_type", "unknown"),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--flows", type=Path, required=True, help="CSV de flow_extractor")
    p.add_argument("--manifests", type=Path, required=True, help="Carpeta con attack_*.json")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    by_ip = load_zones()
    manifests = load_manifests(args.manifests)
    print(f"manifests cargados: {len(manifests)}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    with args.flows.open("r", encoding="utf-8") as inp, \
         args.out.open("w", newline="", encoding="utf-8") as outp:
        reader = csv.DictReader(inp)
        writer = None
        n = 0
        for r in reader:
            labeled = label_row(r, manifests, by_ip)
            if writer is None:
                writer = csv.DictWriter(outp, fieldnames=list(labeled.keys()))
                writer.writeheader()
            writer.writerow(labeled)
            counts[labeled["label"]] = counts.get(labeled["label"], 0) + 1
            n += 1
            if n % 200000 == 0:
                print(f"  {n} filas etiquetadas")

    print(f"Etiquetado → {args.out} ({n} filas)")
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {k:<24} {v}")


if __name__ == "__main__":
    main()
