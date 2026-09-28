#!/usr/bin/env python3
"""
Bridge entre el detector ML y el controlador SDN.

  flujos (CSV/streaming) → modelo (rf.joblib) → predict_proba
       → si label != BENIGN
       → POST http://controller:8080/iot/mitigate

Política de decisión:
  - confianza >= 0.85 ∧ familia ∈ {ddos, amplification, botnet_ddos}
       → action=drop, duration=120s
  - confianza >= 0.75 ∧ familia ∈ {recon, protocol_abuse, bruteforce}
       → action=limit, rate_kbps=512, duration=180s
  - confianza  < 0.75
       → solo log (no acción)

Modos:
  --once     procesa el CSV de un run y termina
  --watch    monitoriza un archivo CSV y procesa filas nuevas (tail-like)
  --replay   re-procesa todo el CSV con sleep para emular tiempo real
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "ml_extra" / "artifacts"


FAMILY_MAP = {
    "BENIGN": "benign",
    "SYN_FLOOD": "ddos", "UDP_FLOOD": "ddos", "ICMP_FLOOD": "ddos", "HTTP_FLOOD": "ddos",
    "SLOWLORIS": "dos_low_rate",
    "PORT_SCAN": "recon",
    "ARP_SPOOF": "mitm",
    "DNS_AMPLIFICATION": "amplification",
    "COAP_AMPLIFICATION": "amplification",
    "SSDP_AMPLIFICATION": "amplification",
    "MQTT_SUBSCRIBE_FLOOD": "protocol_abuse",
    "MQTT_MALFORMED": "protocol_abuse",
    "CREDENTIAL_BRUTEFORCE": "bruteforce",
    "MIRAI_COORDINATED": "botnet_ddos",
}


def decide(label: str, confidence: float) -> dict | None:
    if label == "BENIGN":
        return None
    family = FAMILY_MAP.get(label, "unknown")
    if confidence >= 0.85 and family in {"ddos", "amplification", "botnet_ddos"}:
        return {"action": "drop", "duration_s": 120}
    if confidence >= 0.75 and family in {"recon", "protocol_abuse", "bruteforce", "dos_low_rate", "mitm"}:
        return {"action": "limit", "rate_kbps": 512, "duration_s": 180}
    return None


class Detector:
    def __init__(self, artifacts: Path, controller_url: str):
        import joblib
        self.controller = controller_url.rstrip("/")
        self.model = joblib.load(artifacts / "mlp.joblib")
        self.scaler = joblib.load(artifacts / "scaler.joblib")
        self.le = joblib.load(artifacts / "label_encoder.joblib")
        self.feature_names: list[str] = joblib.load(artifacts / "feature_names.joblib")
        self.recent_actions: dict[str, float] = {}  # debounce: src_ip → ts
        self.cooldown_s = 30
        self.classes = list(self.le.classes_)

    def predict_row(self, row: dict) -> tuple[str, float]:
        import numpy as np
        x = np.zeros((1, len(self.feature_names)), dtype=np.float64)
        for i, name in enumerate(self.feature_names):
            v = row.get(name, 0)
            try:
                x[0, i] = float(v) if v not in (None, "") else 0.0
            except (TypeError, ValueError):
                x[0, i] = 0.0
        x = self.scaler.transform(x)
        if hasattr(self.model, "predict_proba"):
            proba = self.model.predict_proba(x)[0]
            idx = int(np.argmax(proba))
            return self.classes[idx], float(proba[idx])
        return self.classes[int(self.model.predict(x)[0])], 1.0

    def react(self, src_ip: str, label: str, confidence: float) -> dict | None:
        if not src_ip or src_ip == "0.0.0.0":
            return None
        now = time.time()
        if now - self.recent_actions.get(src_ip, 0) < self.cooldown_s:
            return None
        decision = decide(label, confidence)
        if decision is None:
            return None
        self.recent_actions[src_ip] = now

        body = {"src_ip": src_ip, **decision}
        url = f"{self.controller}/iot/mitigate"
        try:
            from dashboard.audit_log import log_event
        except Exception:
            log_event = lambda *a, **k: None  # noqa: E731
        try:
            req = urllib.request.Request(
                url, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(req, timeout=3) as r:
                resp = json.loads(r.read())
            print(f"[ACTION] {src_ip} {label} ({confidence:.2f}) → {decision['action']} ok dpids={resp.get('dpids')}")
            log_event("mitigate", src_ip=src_ip, label=label,
                      confidence=confidence, **decision, dpids=resp.get("dpids", []))
            return resp
        except urllib.error.URLError as e:
            print(f"[ERR] mitigate {src_ip}: {e}", file=sys.stderr)
            log_event("mitigate_failed", src_ip=src_ip, label=label,
                      confidence=confidence, error=str(e))
            return None


def process_csv(det: Detector, path: Path, *, replay: bool = False, watch: bool = False) -> None:
    if watch:
        _tail(det, path)
        return

    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        last_ts = None
        for row in reader:
            label, conf = det.predict_row(row)
            det.react(row.get("src_ip", ""), label, conf)
            if replay and row.get("start_ts"):
                ts = float(row["start_ts"])
                if last_ts is not None:
                    dt = ts - last_ts
                    if 0 < dt < 5:
                        time.sleep(dt)
                last_ts = ts


def _tail(det: Detector, path: Path) -> None:
    print(f"[WATCH] {path}")
    while not path.exists():
        time.sleep(1)
    with path.open("r", encoding="utf-8") as f:
        header = next(csv.reader(f), None)
        if not header:
            print("[WATCH] CSV vacío")
            return
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.5)
                continue
            row = dict(zip(header, next(csv.reader([line]))))
            label, conf = det.predict_row(row)
            det.react(row.get("src_ip", ""), label, conf)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--controller", default=os.getenv("CONTROLLER_URL", "http://controller:8080"))
    p.add_argument("--artifacts", type=Path, default=ARTIFACTS)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--once", action="store_true", help="procesa todo el CSV una vez")
    g.add_argument("--replay", action="store_true", help="emula tiempo real con sleeps")
    g.add_argument("--watch", action="store_true", help="tail del CSV (filas nuevas)")
    args = p.parse_args()

    det = Detector(args.artifacts, args.controller)
    print(f"[INIT] modelo cargado, {len(det.classes)} clases, controller={args.controller}")
    process_csv(det, args.csv, replay=args.replay, watch=args.watch)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
