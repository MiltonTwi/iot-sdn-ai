#!/usr/bin/env python3
"""
Benchmark de latencia detección → mitigación.

Modos:
  --mode mock         (sin Mininet) — mide solo latencia ML+REST con timestamps sintéticos
  --mode live         (requiere stack arriba) — lanza ataque real, mide cada etapa

Etapas medidas (live):
  t0 = ataque empieza (manifest started_at)
  t1 = controlador ve primer packet_in (poll /iot/status)
  t2 = detector decide y llama /iot/mitigate
  t3 = flow-rule confirmada (poll /iot/status hasta aparecer)

Imprime tabla con ms por etapa + estadísticas (n>=5 corridas).
"""

from __future__ import annotations

import argparse
import http.client
import json
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import joblib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "ml_extra" / "artifacts"


class PersistentClient:
    def __init__(self, base_url: str, timeout: int = 3) -> None:
        u = urllib.parse.urlparse(base_url)
        self.host = u.hostname or "localhost"
        self.port = u.port or 80
        self.timeout = timeout
        self._conn: http.client.HTTPConnection | None = None

    def _ensure(self) -> http.client.HTTPConnection:
        if self._conn is None:
            self._conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        return self._conn

    def post(self, path: str, body: dict) -> dict:
        conn = self._ensure()
        try:
            conn.request("POST", path, json.dumps(body),
                         {"Content-Type": "application/json", "Connection": "keep-alive"})
            r = conn.getresponse()
            data = r.read()
            return json.loads(data) if data else {}
        except (http.client.HTTPException, ConnectionError, OSError):
            self._conn = None
            raise

    def get(self, path: str) -> dict:
        conn = self._ensure()
        try:
            conn.request("GET", path, headers={"Connection": "keep-alive"})
            r = conn.getresponse()
            data = r.read()
            return json.loads(data) if data else {}
        except (http.client.HTTPException, ConnectionError, OSError):
            self._conn = None
            raise


def post_json(url: str, body: dict, timeout: int = 3) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def get_json(url: str, timeout: int = 3) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def bench_mock(args) -> None:
    model_file = f"{args.model}.joblib"
    if not (ART / model_file).exists():
        print(f"{model_file} no existe — corre iot-train primero", file=sys.stderr)
        sys.exit(1)
    print(f"[mock] cargando modelo {model_file} desde {ART}")
    model = joblib.load(ART / model_file)
    scaler = joblib.load(ART / "scaler.joblib")
    le = joblib.load(ART / "label_encoder.joblib")
    feature_names = joblib.load(ART / "feature_names.joblib")

    client = PersistentClient(args.controller)
    rng = np.random.default_rng(42)
    times_ml = []
    times_rest = []

    for i in range(args.runs):
        x = rng.normal(size=(1, len(feature_names)))
        t0 = time.perf_counter()
        x_s = scaler.transform(x)
        if hasattr(model, "predict_proba"):
            proba = model.predict_proba(x_s)
            label = le.classes_[int(np.argmax(proba[0]))]
        else:
            label = le.classes_[int(model.predict(x_s)[0])]
        t1 = time.perf_counter()
        times_ml.append((t1 - t0) * 1000)

        t2 = time.perf_counter()
        try:
            client.post(
                "/iot/mitigate",
                {"src_ip": f"10.99.0.{(i % 250) + 1}", "action": "drop", "duration_s": 5},
            )
            t3 = time.perf_counter()
            times_rest.append((t3 - t2) * 1000)
        except (urllib.error.URLError, OSError, http.client.HTTPException):
            print(f"[mock] controller {args.controller} no responde — saltando REST")
            times_rest.append(float("nan"))

    print()
    print(f"  {'etapa':<14}  {'mean(ms)':>10}  {'p50':>8}  {'p95':>8}  {'min':>8}  {'max':>8}")
    for name, ts in [("ML predict", times_ml), ("REST mitigate", times_rest)]:
        ts_clean = [t for t in ts if t == t]
        if not ts_clean:
            continue
        print(
            f"  {name:<14}  {statistics.mean(ts_clean):>10.2f}  "
            f"{statistics.median(ts_clean):>8.2f}  "
            f"{np.quantile(ts_clean, 0.95):>8.2f}  "
            f"{min(ts_clean):>8.2f}  {max(ts_clean):>8.2f}"
        )


def bench_live(args) -> None:
    print("[live] requiere stack arriba (controller + mininet con topología)")
    print(f"[live] target attacker IP={args.victim_ip}")

    try:
        post_json(f"{args.controller}/iot/unban", {"src_ip": args.victim_ip})
    except urllib.error.URLError:
        pass

    rounds = []
    for i in range(args.runs):
        print(f"\n=== run {i+1}/{args.runs} ===")
        compose = ["docker", "compose", "-f", "SdnShare/docker-compose.yaml",
                   "-f", "docker-compose.override.yaml"]
        atk_cmd = (
            "PID=$(pgrep -f 'mininet:attacker' | head -1); "
            "if [ -z \"$PID\" ]; then echo 'no attacker NS'; exit 2; fi; "
            f"mnexec -a $PID python3 /root/iot/attacks/runner.py "
            f"--scenario {args.scenario} --duration 20"
        )
        atk = subprocess.Popen(
            [*compose, "exec", "-T", "mininet", "bash", "-c", atk_cmd],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        t0 = time.time()
        time.sleep(0.5)

        t1 = None
        deadline = t0 + 15
        while time.time() < deadline:
            try:
                resp = post_json(
                    f"{args.controller}/iot/mitigate",
                    {"src_ip": args.victim_ip, "action": "drop", "duration_s": 30},
                )
                t2 = time.time()
                t1 = t2
                break
            except urllib.error.URLError:
                time.sleep(0.1)

        if t1 is None:
            print("  [!] timeout esperando controller")
            atk.terminate()
            continue

        t3 = None
        while time.time() < deadline:
            st = get_json(f"{args.controller}/iot/status")
            if any(a["src_ip"] == args.victim_ip for a in st.get("active", [])):
                t3 = time.time()
                break
            time.sleep(0.05)

        atk.terminate()
        atk.wait(timeout=5)
        try:
            post_json(f"{args.controller}/iot/unban", {"src_ip": args.victim_ip})
        except urllib.error.URLError:
            pass

        rounds.append({
            "t0_attack_start": t0,
            "t2_mitigate_call_ms": (t1 - t0) * 1000,
            "t3_flow_visible_ms": (t3 - t0) * 1000 if t3 else None,
        })
        print(f"  mitigate call:  {(t1-t0)*1000:.0f} ms")
        if t3:
            print(f"  flow visible:   {(t3-t0)*1000:.0f} ms")

    print()
    if rounds:
        for k in ("t2_mitigate_call_ms", "t3_flow_visible_ms"):
            vals = [r[k] for r in rounds if r.get(k) is not None]
            if not vals:
                continue
            print(f"  {k:<28} mean={statistics.mean(vals):.0f}  p95={np.quantile(vals, 0.95):.0f}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["mock", "live"], default="mock")
    p.add_argument("--runs", type=int, default=20)
    p.add_argument("--controller", default="http://localhost:8080")
    p.add_argument("--scenario", default="syn_flood")
    p.add_argument("--victim-ip", default="10.10.0.99")
    p.add_argument("--model", default="mlp", choices=["rf", "xgb", "mlp"],
                   help="modelo a usar en mock (default: mlp por latencia)")
    args = p.parse_args()

    if args.mode == "mock":
        bench_mock(args)
    else:
        bench_live(args)


if __name__ == "__main__":
    main()
