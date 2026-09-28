#!/usr/bin/env python3
"""
Benchmark integral del sistema IoT-SDN-AI.

Mide 6 dimensiones y vuelca JSON con todos los números crudos:
  1. Latencia ML: 5 modelos × {1, 10, 100, 1000} batch
  2. REST controller: keep-alive vs no-keep-alive (A/B)
  3. REST concurrencia: 1, 10, 50 hilos paralelos
  4. Flow-install: POST /iot/mitigate → flow visible en OVS
  5. Detector throughput: dataset real replay
  6. Per-clase detection latency

Uso:
  python3 scripts/bench_full.py --csv /home/ubuntu/iot_run/dataset_p1p2_clean13.csv
  python3 scripts/bench_full.py --sections ml,rest    # solo algunas

Salida:
  - tabla por sección a stdout
  - JSON consolidado a data/bench/bench_full_<timestamp>.json
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import http.client
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

import joblib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "ml_extra" / "artifacts"
OUT_DIR = ROOT / "data" / "bench"

MODELS = ["rf", "xgb", "mlp", "isoforest", "autoencoder"]
BATCH_SIZES = [1, 10, 100, 1000]


def stats(vals: list[float]) -> dict:
    if not vals:
        return {}
    return {
        "n": len(vals),
        "mean_ms": round(statistics.mean(vals), 3),
        "p50_ms": round(statistics.median(vals), 3),
        "p95_ms": round(float(np.quantile(vals, 0.95)), 3),
        "p99_ms": round(float(np.quantile(vals, 0.99)), 3),
        "min_ms": round(min(vals), 3),
        "max_ms": round(max(vals), 3),
    }


def print_table(title: str, rows: list[tuple]) -> None:
    print(f"\n=== {title} ===")
    if not rows:
        print("  (vacío)")
        return
    header = rows[0]
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(header))]
    for i, r in enumerate(rows):
        line = "  " + "  ".join(str(r[j]).rjust(widths[j]) for j in range(len(r)))
        print(line)
        if i == 0:
            print("  " + "  ".join("-" * w for w in widths))


# --- 1. ML latency ---------------------------------------------------------

def bench_ml(args) -> dict:
    print("\n[1/6] ML latency — 5 modelos × 4 batch sizes")
    sys.path.insert(0, str(ROOT))
    scaler = joblib.load(ART / "scaler.joblib")
    le = joblib.load(ART / "label_encoder.joblib")
    fn = joblib.load(ART / "feature_names.joblib")
    rng = np.random.default_rng(42)
    n_warmup = 5
    n_runs = 50

    results = {}
    table_rows = [("model", "batch", "mean(ms)", "p50", "p95", "per-sample(us)")]
    for m_name in MODELS:
        path = ART / f"{m_name}.joblib"
        if not path.exists():
            print(f"  [skip] {m_name}: no artifact")
            continue
        try:
            m = joblib.load(path)
        except Exception as e:
            print(f"  [skip] {m_name}: load failed ({e.__class__.__name__})")
            continue
        results[m_name] = {}
        for B in BATCH_SIZES:
            ts = []
            x_pool = rng.normal(size=(B + n_warmup, len(fn)))
            for i in range(n_warmup):
                xs = scaler.transform(x_pool[:B])
                _ = (m.predict_proba(xs) if hasattr(m, "predict_proba")
                     else m.predict(xs) if hasattr(m, "predict")
                     else m.decision_function(xs))
            for _ in range(n_runs):
                x = rng.normal(size=(B, len(fn)))
                t0 = time.perf_counter()
                xs = scaler.transform(x)
                if hasattr(m, "predict_proba"):
                    _ = m.predict_proba(xs)
                elif hasattr(m, "predict"):
                    _ = m.predict(xs)
                else:
                    _ = m.decision_function(xs)
                ts.append((time.perf_counter() - t0) * 1000)
            s = stats(ts)
            results[m_name][B] = s
            per_sample_us = s["mean_ms"] / B * 1000
            table_rows.append((m_name, B,
                               f"{s['mean_ms']:.2f}",
                               f"{s['p50_ms']:.2f}",
                               f"{s['p95_ms']:.2f}",
                               f"{per_sample_us:.2f}"))
    print_table("ML latency", table_rows)
    return results


# --- 2. REST keep-alive A/B ------------------------------------------------

def _new_persistent(base: str, timeout: int = 5):
    u = urllib.parse.urlparse(base)
    return http.client.HTTPConnection(u.hostname or "localhost", u.port or 80, timeout=timeout)


def _post_keepalive(conn: http.client.HTTPConnection, path: str, body: dict) -> float:
    t0 = time.perf_counter()
    conn.request("POST", path, json.dumps(body),
                 {"Content-Type": "application/json", "Connection": "keep-alive"})
    r = conn.getresponse()
    r.read()
    return (time.perf_counter() - t0) * 1000


def _post_fresh(base: str, path: str, body: dict, timeout: int = 5) -> float:
    u = urllib.parse.urlparse(base)
    t0 = time.perf_counter()
    c = http.client.HTTPConnection(u.hostname or "localhost", u.port or 80, timeout=timeout)
    c.request("POST", path, json.dumps(body), {"Content-Type": "application/json"})
    r = c.getresponse()
    r.read()
    c.close()
    return (time.perf_counter() - t0) * 1000


def bench_rest(args) -> dict:
    print("\n[2/6] REST — keep-alive A/B (n=100 c/u)")
    base = args.controller
    n = 100
    body_template = {"action": "drop", "duration_s": 1}

    # warmup
    for i in range(5):
        _post_fresh(base, "/iot/mitigate", {**body_template, "src_ip": f"10.99.0.{i+1}"})

    # keep-alive
    conn = _new_persistent(base)
    ts_ka = []
    for i in range(n):
        ts_ka.append(_post_keepalive(conn, "/iot/mitigate",
                                     {**body_template, "src_ip": f"10.97.0.{(i % 250) + 1}"}))
    conn.close()

    # fresh
    ts_fresh = []
    for i in range(n):
        ts_fresh.append(_post_fresh(base, "/iot/mitigate",
                                    {**body_template, "src_ip": f"10.96.0.{(i % 250) + 1}"}))

    s_ka = stats(ts_ka)
    s_fresh = stats(ts_fresh)
    rows = [
        ("modo", "mean(ms)", "p50", "p95", "p99", "min", "max"),
        ("keep-alive", s_ka["mean_ms"], s_ka["p50_ms"], s_ka["p95_ms"],
         s_ka["p99_ms"], s_ka["min_ms"], s_ka["max_ms"]),
        ("fresh-conn", s_fresh["mean_ms"], s_fresh["p50_ms"], s_fresh["p95_ms"],
         s_fresh["p99_ms"], s_fresh["min_ms"], s_fresh["max_ms"]),
    ]
    print_table("REST keep-alive vs fresh", rows)
    improvement = (s_fresh["p50_ms"] - s_ka["p50_ms"]) / s_fresh["p50_ms"] * 100
    print(f"\n  → keep-alive baja p50 en {improvement:.1f}%")
    return {"keepalive": s_ka, "fresh": s_fresh, "improvement_pct": improvement}


# --- 3. REST concurrencia --------------------------------------------------

def _conc_worker(base: str, idx: int, calls_per_worker: int) -> list[float]:
    conn = _new_persistent(base)
    out = []
    for i in range(calls_per_worker):
        try:
            out.append(_post_keepalive(conn, "/iot/mitigate", {
                "src_ip": f"10.{90+idx}.0.{(i % 250) + 1}",
                "action": "drop", "duration_s": 1,
            }))
        except Exception:
            out.append(float("nan"))
    conn.close()
    return [t for t in out if t == t]


def bench_rest_concurrency(args) -> dict:
    print("\n[3/6] REST concurrencia — 1, 10, 50 hilos paralelos × 30 calls c/u")
    results = {}
    rows = [("workers", "calls_total", "wall(ms)", "throughput/s", "mean_lat(ms)", "p95")]
    for W in [1, 10, 50]:
        with concurrent.futures.ThreadPoolExecutor(max_workers=W) as ex:
            t0 = time.perf_counter()
            futures = [ex.submit(_conc_worker, args.controller, i, 30) for i in range(W)]
            all_lat = []
            for f in concurrent.futures.as_completed(futures):
                all_lat.extend(f.result())
            wall_ms = (time.perf_counter() - t0) * 1000
        s = stats(all_lat)
        throughput = len(all_lat) / (wall_ms / 1000) if wall_ms else 0
        rows.append((W, len(all_lat), f"{wall_ms:.0f}", f"{throughput:.0f}",
                     f"{s['mean_ms']:.2f}", f"{s['p95_ms']:.2f}"))
        results[W] = {"wall_ms": wall_ms, "throughput_s": throughput, **s}
    print_table("REST concurrencia", rows)
    return results


# --- 4. Flow install latency -----------------------------------------------

def bench_flow_install(args) -> dict:
    print("\n[4/6] Flow install — tiempo POST → flow visible en OVS (n=20)")
    base = args.controller
    conn = _new_persistent(base)

    # cleanup
    for i in range(20):
        try:
            _post_fresh(base, "/iot/unban", {"src_ip": f"10.88.0.{i+1}"})
        except Exception:
            pass

    ts = []
    for i in range(20):
        ip = f"10.88.0.{i+1}"
        t0 = time.perf_counter()
        _post_keepalive(conn, "/iot/mitigate", {"src_ip": ip, "action": "drop", "duration_s": 60})
        t_post = time.perf_counter()

        # poll /iot/status
        t_visible = None
        deadline = time.perf_counter() + 3
        while time.perf_counter() < deadline:
            try:
                gc = _new_persistent(base, timeout=2)
                gc.request("GET", "/iot/status", headers={"Connection": "close"})
                r = gc.getresponse()
                data = json.loads(r.read())
                gc.close()
                if any(a.get("src_ip") == ip for a in data.get("active", [])):
                    t_visible = time.perf_counter()
                    break
            except Exception:
                pass
            time.sleep(0.005)
        if t_visible:
            ts.append({
                "post_ms": (t_post - t0) * 1000,
                "visible_ms": (t_visible - t0) * 1000,
                "delta_ms": (t_visible - t_post) * 1000,
            })
        # cleanup
        try:
            _post_keepalive(conn, "/iot/unban", {"src_ip": ip})
        except Exception:
            pass
    conn.close()

    if not ts:
        print("  (sin datos)")
        return {}

    s_post = stats([t["post_ms"] for t in ts])
    s_visible = stats([t["visible_ms"] for t in ts])
    s_delta = stats([t["delta_ms"] for t in ts])
    rows = [
        ("etapa", "mean(ms)", "p50", "p95", "min", "max"),
        ("POST returns", s_post["mean_ms"], s_post["p50_ms"], s_post["p95_ms"], s_post["min_ms"], s_post["max_ms"]),
        ("flow visible", s_visible["mean_ms"], s_visible["p50_ms"], s_visible["p95_ms"], s_visible["min_ms"], s_visible["max_ms"]),
        ("delta (post→visible)", s_delta["mean_ms"], s_delta["p50_ms"], s_delta["p95_ms"], s_delta["min_ms"], s_delta["max_ms"]),
    ]
    print_table("Flow install latency", rows)
    return {"post": s_post, "visible": s_visible, "delta": s_delta}


# --- 5. Detector throughput + 6. per-class ---------------------------------

def bench_detector(args) -> dict:
    print("\n[5-6/6] Detector throughput + per-class latency (dataset real)")
    if not args.csv or not args.csv.exists():
        print(f"  [skip] CSV no encontrado: {args.csv}")
        return {}
    sys.path.insert(0, str(ROOT))
    from dashboard.detector_service import Detector

    det = Detector(ART, args.controller)
    det.cooldown_s = 0
    print(f"  modelo cargado, {len(det.classes)} clases, csv={args.csv}")

    per_ip: dict[str, dict] = {}
    per_class_latencies: dict[str, list[float]] = {}
    n_rows = 0
    n_mitigated = 0
    t_start = time.perf_counter()

    with args.csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            n_rows += 1
            src = row.get("src_ip", "")
            if not src:
                continue
            entry = per_ip.get(src)
            if entry and entry.get("done"):
                continue
            t_in = time.perf_counter()
            label, conf = det.predict_row(row)
            if label == "BENIGN":
                if entry is None:
                    per_ip[src] = {"benign_first_in": t_in, "done": False}
                continue
            # first malicious row for this src_ip
            if entry is None or "malic_first_in" not in entry:
                per_ip.setdefault(src, {})
                per_ip[src]["malic_first_in"] = t_in
            resp = det.react(src, label, conf)
            t_react = time.perf_counter()
            if resp is not None:
                latency_ms = (t_react - per_ip[src]["malic_first_in"]) * 1000
                per_ip[src]["done"] = True
                per_ip[src]["latency_ms"] = latency_ms
                per_ip[src]["label"] = label
                per_class_latencies.setdefault(label, []).append(latency_ms)
                n_mitigated += 1

    elapsed = time.perf_counter() - t_start
    throughput = n_rows / elapsed
    print(f"\n  rows={n_rows}  IPs={len(per_ip)}  mitigated={n_mitigated}")
    print(f"  wall={elapsed:.1f}s  throughput={throughput:.0f} flows/s")

    rows = [("clase", "n", "mean(ms)", "p50", "p95", "min", "max")]
    for cls, lats in sorted(per_class_latencies.items(), key=lambda x: -len(x[1])):
        s = stats(lats)
        rows.append((cls, s["n"], f"{s['mean_ms']:.2f}",
                     f"{s['p50_ms']:.2f}", f"{s['p95_ms']:.2f}",
                     f"{s['min_ms']:.2f}", f"{s['max_ms']:.2f}"))
    print_table("Latencia por clase de ataque", rows)

    return {
        "rows_processed": n_rows,
        "ips_seen": len(per_ip),
        "ips_mitigated": n_mitigated,
        "wall_s": elapsed,
        "throughput_flows_s": throughput,
        "per_class": {k: stats(v) for k, v in per_class_latencies.items()},
    }


# --- 7. System resources (snapshot) ----------------------------------------

def bench_resources(args) -> dict:
    print("\n[extra] Recursos del sistema (snapshot)")
    out = {}
    try:
        r = subprocess.run(["docker", "stats", "--no-stream", "--format",
                            "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"],
                           capture_output=True, text=True, timeout=10)
        out["docker_stats"] = r.stdout.strip().splitlines()
        for line in out["docker_stats"]:
            print(f"  {line}")
    except Exception as e:
        out["docker_stats_error"] = str(e)
    try:
        r = subprocess.run(["free", "-h"], capture_output=True, text=True, timeout=5)
        out["free"] = r.stdout
    except Exception:
        pass
    return out


# --- main ------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--controller", default="http://localhost:8080")
    p.add_argument("--csv", type=Path, default=Path("/home/ubuntu/iot_run/dataset_p1p2_clean13.csv"))
    p.add_argument("--sections", default="ml,rest,conc,flow,det,res",
                   help="coma-separado: ml,rest,conc,flow,det,res")
    args = p.parse_args()
    sections = set(args.sections.split(","))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts_run = time.strftime("%Y%m%d-%H%M%S")
    out_path = OUT_DIR / f"bench_full_{ts_run}.json"

    results = {"timestamp": ts_run, "sections_run": sorted(sections)}
    if "ml" in sections:
        results["ml"] = bench_ml(args)
    if "rest" in sections:
        results["rest_ab"] = bench_rest(args)
    if "conc" in sections:
        results["rest_concurrency"] = bench_rest_concurrency(args)
    if "flow" in sections:
        results["flow_install"] = bench_flow_install(args)
    if "det" in sections:
        results["detector"] = bench_detector(args)
    if "res" in sections:
        results["resources"] = bench_resources(args)

    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\n[done] JSON guardado en {out_path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
