#!/usr/bin/env python3
"""Experimento de lazo cerrado: ataques reales → detector en vivo → mitigación SDN.

Corre en la VM (host de docker). Por cada escenario lanza el ataque real en
Mininet con `live_capture.sh` + `live_detector.py` activos (sin intervención
manual) y mide:

- **TTM** (time-to-mitigate): inicio del ataque → primera regla instalada.
- **Acierto de la regla**: el match contiene al atacante / al par
  víctima-reflector / al destino protegido (ataques con origen falsificado).
- **Efecto en la víctima**: paquetes/s recibidos antes vs. después de la regla
  (contador rx de la interfaz de la víctima, muestreado cada 1 s).
- **Falsas alarmas**: acciones durante el periodo solo-benigno y acciones sobre
  dispositivos benignos durante los ataques (daño colateral).

  python3 ml_extra/closed_loop_eval.py [--benign-s 120] [--attack-s 40]
Salida: ml_extra/artifacts/closed_loop.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "ml_extra" / "artifacts"
LIVE = ROOT / "data" / "live"
CTN = "sdnshare-mininet-1"
CTRL = "http://localhost:8080"
ATTACKER_IP = "10.10.0.99"

SCENARIOS = ["syn_flood", "udp_flood", "icmp_flood", "http_flood", "slowloris", "port_scan",
             "dns_amplification", "coap_amplification", "ssdp_amplification",
             "mqtt_subscribe_flood", "mqtt_malformed", "credential_bruteforce",
             "mirai_coordinated"]


def dexec(cmd: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "exec", CTN, "bash", "-c", cmd],
                          capture_output=True, text=True, **kw)


def api(path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        CTRL + path, data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def unban_all() -> None:
    for a in api("/iot/status")["active"]:
        api("/iot/unban", a["match"])


def host_pid(name: str) -> str:
    return dexec(f"pgrep -f 'is mininet:{name}$' | head -1").stdout.strip()


class RxSampler(threading.Thread):
    """Muestrea rx_packets de la víctima cada 1 s (dentro de su namespace)."""

    def __init__(self, pid: str, seconds: int):
        super().__init__(daemon=True)
        self.pid, self.seconds, self.samples = pid, seconds, []

    def run(self) -> None:
        # /proc/net/dev es por netns (/sys no: mnexec no remonta sysfs). La
        # interfaz del host no siempre es -eth0 (httpserve-eth5): primera no-lo.
        awk = "NR>2 && $1!=\"lo:\"{sub(/.*:/,\"\");print $2;exit}"
        cmd = (f"for i in $(seq {self.seconds}); do echo $(date +%s.%N) "
               f"$(mnexec -a {self.pid} awk '{awk}' /proc/net/dev); "
               f"sleep 1; done")
        p = subprocess.Popen(["docker", "exec", CTN, "bash", "-c", cmd],
                             stdout=subprocess.PIPE, text=True)
        for line in p.stdout:
            parts = line.split()
            if len(parts) == 2:
                self.samples.append((float(parts[0]), int(parts[1])))


def pps_series(samples) -> list[tuple[float, float]]:
    """(t, pps) por intervalo de ~1 s entre muestras consecutivas del contador rx."""
    return [(b[0], (b[1] - a[1]) / (b[0] - a[0]))
            for a, b in zip(samples, samples[1:]) if b[0] > a[0]]


def victim_effect(samples, t0: float, t_rule: float, t_end: float) -> dict:
    """Pico antes de la regla vs. media tras la regla (la regla llega en pocos
    segundos: no hay ventana previa larga que promediar)."""
    s = pps_series(samples)
    base = [p for t, p in s if t <= t0]
    pre = [p for t, p in s if t0 < t <= t_rule + 1]
    post = [p for t, p in s if t_rule + 2 <= t <= t_end]
    r = {"baseline_pps": round(sum(base) / len(base), 1) if base else None,
         "peak_pps_pre": round(max(pre), 1) if pre else None,
         "mean_pps_post": round(sum(post) / len(post), 1) if post else None}
    if pre and post and max(pre) > 0:
        r["reduction_pct"] = round(100 * (1 - (sum(post) / len(post)) / max(pre)), 1)
    return r


def read_actions(since: float) -> list[dict]:
    f = LIVE / "actions.jsonl"
    if not f.exists():
        return []
    rows = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return [r for r in rows if r["ts"] >= since]


def correct(sc: dict, match: dict, bots: set[str]) -> bool:
    src, dst = match.get("src_ip"), match.get("dst_ip")
    if src == ATTACKER_IP or src in bots:
        return True
    if dst == ATTACKER_IP:  # respuestas de la víctima al atacante: inocuo, sigue conteniendo
        return True
    if "reflector_ip" in sc:  # amplificación: consultas falsificadas → reflector, o respuestas
        vnet = sc["victim_ip"].rsplit(".", 1)[0] + "."
        if dst == sc["reflector_ip"]:
            return src is None or src.startswith(vnet)
        return src == sc["reflector_ip"] and bool(dst) and dst.startswith(vnet)
    if src is None and dst == sc.get("target_ip"):  # destino protegido (origen falso)
        return True
    spoof = sc.get("spoof_base_ip") or sc.get("botnet_base_ip")
    return bool(spoof and src and src.rsplit(".", 1)[0] == spoof.rsplit(".", 1)[0]
                and int(src.rsplit(".", 1)[1]) >= int(spoof.rsplit(".", 1)[1]))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--benign-s", type=int, default=120)
    p.add_argument("--attack-s", type=int, default=40)
    p.add_argument("--cooldown-s", type=int, default=20)
    p.add_argument("--scenarios", nargs="*", default=SCENARIOS)
    p.add_argument("--out", default="closed_loop.json", help="nombre del JSON en artifacts/")
    p.add_argument("--chunk-s", type=float, default=5.0, help="ventana de captura en vivo (s)")
    args = p.parse_args()

    catalog = {s["id"]: s for s in yaml.safe_load(
        (ROOT / "iot/attacks/catalog.yaml").read_text(encoding="utf-8"))["scenarios"]}
    hosts = json.loads(dexec("cat /tmp/iot_hosts.json").stdout)
    ip2name = {h["ip"]: h["name"] for h in hosts}
    orig2ip = {h["original_name"]: h["ip"] for h in hosts}
    benign_ips = {h["ip"] for h in hosts if h["zone"] != "infra"}

    LIVE.mkdir(parents=True, exist_ok=True)
    (LIVE / "actions.jsonl").unlink(missing_ok=True)
    unban_all()
    print(dexec(f"bash /root/iot/pipeline/live_capture.sh start {args.chunk_s:g}").stdout.strip())
    det_log = open("/tmp/live_detector.log", "w")
    det = subprocess.Popen(["python3", str(ROOT / "ml_extra/live_detector.py"),
                            "--live-dir", str(LIVE), "--controller", CTRL,
                            "--chunk-s", str(args.chunk_s)],
                           stdout=det_log, stderr=subprocess.STDOUT)
    result = {"attack_s": args.attack_s, "benign_s": args.benign_s, "chunk_s": args.chunk_s,
              "scenarios": {}}
    try:
        time.sleep(10)  # arranque de captura + carga de modelos
        t_b = time.time()
        print(f">>> periodo benigno {args.benign_s}s")
        time.sleep(args.benign_s)
        fp = read_actions(t_b)
        result["benign"] = {"duration_s": args.benign_s, "false_actions": len(fp), "actions": fp}
        print(f"    falsas alarmas: {len(fp)}")
        unban_all()

        for sid in args.scenarios:
            sc = catalog[sid]
            bots = {orig2ip[b] for b in sc.get("bots", []) if b in orig2ip}
            # amplificación: se mide en el REFLECTOR (consultas que alimentan la
            # amplificación). En el lab la "víctima" no recibe respuestas: recibe
            # ~150 ARP/s del reflector resolviendo las IPs falsificadas del /24.
            victim_ip = sc.get("reflector_ip") or sc.get("victim_ip") or sc.get("target_ip")
            sampler = None
            if victim_ip in ip2name:
                sampler = RxSampler(host_pid(ip2name[victim_ip]), args.attack_s + 8)
                sampler.start()
            time.sleep(3)  # línea base previa
            t0 = time.time()
            print(f">>> {sid} ({args.attack_s}s)")
            dexec(f"PID=$(pgrep -f 'is mininet:attacker$' | head -1); mnexec -a $PID "
                  f"python3 /root/iot/attacks/runner.py --scenario {sid} "
                  f"--duration {args.attack_s} --episode 1 >/dev/null 2>&1",
                  timeout=args.attack_s + 120)
            t_end = time.time()
            time.sleep(8)  # último chunk
            acts = read_actions(t0)
            if sampler:
                sampler.join(timeout=15)
            good = [a for a in acts if correct(sc, a["match"], bots)]
            collateral = [a for a in acts if not correct(sc, a["match"], bots)
                          and a["match"].get("src_ip") in benign_ips - bots
                          and a["match"].get("src_ip") != sc.get("victim_ip")]
            first = min((a["ts"] for a in good), default=None)
            r = {"detected": bool(good), "ttm_s": round(first - t0, 2) if first else None,
                 "n_actions": len(acts), "n_correct": len(good), "collateral": len(collateral),
                 "labels": sorted({a["label"] for a in acts}),
                 "actions": [{k: a[k] for k in ("match", "action", "label", "n_flows",
                                                "reason", "latency_s")} | {"t_rel": round(a["ts"] - t0, 2)}
                             for a in acts]}
            if sampler and sampler.samples and first:
                r["victim"] = victim_effect(sampler.samples, t0, first, t_end)
            result["scenarios"][sid] = r
            print(f"    detectado={r['detected']} ttm={r['ttm_s']}s acciones={len(acts)} "
                  f"correctas={len(good)} colateral={len(collateral)} "
                  f"labels={r['labels']} victima={r.get('victim')}")
            unban_all()
            time.sleep(args.cooldown_s)
    finally:
        det.terminate()
        dexec("bash /root/iot/pipeline/live_capture.sh stop")
        unban_all()

    sc = result["scenarios"].values()
    ttms = [s["ttm_s"] for s in sc if s["ttm_s"] is not None]
    result["summary"] = {
        "scenarios": len(result["scenarios"]),
        "detected": sum(s["detected"] for s in sc),
        "ttm_median_s": sorted(ttms)[len(ttms) // 2] if ttms else None,
        "ttm_max_s": max(ttms) if ttms else None,
        "benign_false_actions": result["benign"]["false_actions"],
        "collateral_actions": sum(s["collateral"] for s in sc),
    }
    (ART / args.out).write_text(json.dumps(result, indent=2))
    print(json.dumps(result["summary"], indent=2))
    print("→", ART / args.out)


if __name__ == "__main__":
    main()
