#!/usr/bin/env python3
"""Re-puntúa closed_loop.json (acierto de reglas + atribución) sin repetir el experimento."""
import json
import sys
from pathlib import Path

import yaml

import closed_loop_eval as cle

ROOT = Path(__file__).resolve().parents[1]
f = cle.ART / (sys.argv[1] if len(sys.argv) > 1 else "closed_loop.json")
d = json.loads(f.read_text())
catalog = {s["id"]: s for s in yaml.safe_load(
    (ROOT / "iot/attacks/catalog.yaml").read_text(encoding="utf-8"))["scenarios"]}
bot_ips = {"cam_front": "10.10.1.10", "cam_back": "10.10.1.11", "bulb_living": "10.10.1.14",
           "smart_plug_a": "10.10.1.23", "vacuum": "10.10.1.22"}
attr_ok = 0
for sid, r in d["scenarios"].items():
    sc = catalog[sid]
    bots = {bot_ips[b] for b in sc.get("bots", []) if b in bot_ips}
    good = [a for a in r["actions"] if cle.correct(sc, a["match"], bots)]
    r["n_correct"] = len(good)
    first = min(good, key=lambda a: a["t_rel"]) if good else None
    r["first_label"] = first["label"] if first else None
    r["attribution_ok"] = bool(first and first["label"] == sc["label"])
    attr_ok += r["attribution_ok"]
    print(f"{sid:22} correctas={len(good)}/{len(r['actions'])} 1ª={r['first_label']} ok={r['attribution_ok']}")
s = d["summary"]
s["rules_correct"] = sum(r["n_correct"] for r in d["scenarios"].values())
s["rules_total"] = sum(r["n_actions"] for r in d["scenarios"].values())
s["attribution_correct"] = attr_ok
red = [r["victim"]["reduction_pct"] for r in d["scenarios"].values()
       if r.get("victim", {}).get("reduction_pct") is not None]
s["reduction_median_pct"] = sorted(red)[len(red) // 2]
s["reduction_min_pct"] = min(red)
f.write_text(json.dumps(d, indent=2))
print(json.dumps(s, indent=2))
