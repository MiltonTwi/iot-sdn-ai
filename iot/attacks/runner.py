#!/usr/bin/env python3
"""
Lanza un escenario del catálogo.

Uso:
  sudo python3 iot/attacks/runner.py --scenario syn_flood --duration 60
  sudo python3 iot/attacks/runner.py --list

Diseñado para correr DENTRO del container mininet (donde el attacker host es
un namespace de red Mininet); o vía `mininet> attacker python3 ...`.

Genera además un manifest JSON en /tmp/attack_<ts>.json con start/end/label
para que el labeler del pipeline cruce contra él.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import yaml

CATALOG = Path(__file__).resolve().parent / "catalog.yaml"
SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios"


def load_catalog() -> dict:
    with CATALOG.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def find_scenario(scenarios: list[dict], sid: str) -> dict | None:
    for s in scenarios:
        if s["id"] == sid:
            return s
    return None


# Parámetros de intensidad que se aleatorizan por episodio (×U[0.5, 1.5]).
# Episodios con distinta intensidad + distinta fuente = grupos independientes
# para la CV anti-fuga (ver ml_extra/common.py).
JITTER_KEYS = ("rate_pps", "rate_pps_per_bot", "concurrency", "sockets", "keepalive_s")


def jitter_params(sc: dict, episode: int) -> dict:
    import random

    rng = random.Random(f"{sc['id']}#{episode}")
    out = dict(sc)
    for k in JITTER_KEYS:
        if isinstance(out.get(k), (int, float)):
            v = out[k] * rng.uniform(0.5, 1.5)
            out[k] = max(1, int(round(v))) if isinstance(sc[k], int) else v
    return out


def own_ip() -> str | None:
    """IP de este namespace (host Mininet desde el que se lanza el ataque)."""
    import socket

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.10.0.12", 9))  # UDP connect: no envía nada, solo resuelve ruta
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


def run(sc: dict, duration_override: int | None, episode: int | None = None) -> int:
    # importa dinámicamente el módulo del escenario
    sys.path.insert(0, str(SCENARIOS_DIR.parent.parent.parent))
    mod_name = f"iot.attacks.scenarios.{sc['id']}"
    try:
        module = __import__(mod_name, fromlist=["run"])
    except ModuleNotFoundError:
        print(f"[!] No existe módulo: {mod_name}", file=sys.stderr)
        return 2

    duration = duration_override or sc.get("duration_s", 60)
    sc = {**sc, "duration_s": duration}
    if episode is not None:
        sc = jitter_params(sc, episode)

    ts0 = time.time()
    manifest = {
        "scenario": sc["id"],
        "label": sc["label"],
        "family": sc["family"],
        "started_at": ts0,
        "episode": f"{sc['id']}#{episode if episode is not None else 0}",
        "src_ip": own_ip(),
        "config": sc,
    }
    print(f"[+] {sc['label']} → duración={duration}s episodio={manifest['episode']} "
          f"src={manifest['src_ip']}", flush=True)
    rc = module.run(sc)
    ts1 = time.time()
    manifest["finished_at"] = ts1
    manifest["return_code"] = rc

    ep = f"_ep{episode}" if episode is not None else ""
    out = Path(f"/tmp/attack_{int(ts0)}_{sc['id']}{ep}.json")
    out.write_text(json.dumps(manifest, indent=2))
    print(f"[+] Manifest: {out}")
    return rc


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--scenario")
    p.add_argument("--duration", type=int, default=None)
    p.add_argument("--episode", type=int, default=None, help="nº de episodio: aleatoriza intensidad (seed por episodio)")
    p.add_argument("--list", action="store_true")
    args = p.parse_args()

    cat = load_catalog()
    if args.list:
        for s in cat["scenarios"]:
            print(f"  {s['id']:<24}  {s['family']:<14}  {s['description']}")
        return

    if not args.scenario:
        p.error("--scenario requerido (o --list)")
    sc = find_scenario(cat["scenarios"], args.scenario)
    if sc is None:
        p.error(f"escenario desconocido: {args.scenario}")
    sys.exit(run(sc, args.duration, args.episode))


if __name__ == "__main__":
    main()
