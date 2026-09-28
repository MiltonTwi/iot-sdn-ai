"""SYN scan — usa nmap si está, sino TCP connect scan stdlib."""

from __future__ import annotations

import ipaddress
import shutil
import socket
import subprocess
import time


def run(cfg: dict) -> int:
    duration = cfg["duration_s"]
    end = time.time() + duration
    ports = cfg.get("ports", [22, 80, 443, 1883, 5683])

    if shutil.which("nmap"):
        for net in cfg["targets_subnets"]:
            if time.time() >= end:
                break
            subprocess.run(
                ["nmap", "-sS", "-Pn", "-p", ",".join(map(str, ports)), net,
                 "--max-rate", "2000"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=duration,
            )
        return 0

    # fallback: TCP connect scan paralelo sobre (ip, port) barajados.
    # El secuencial desde .1 gastaba el episodio en IPs inexistentes (solo ARP,
    # sin flujos IP) y casi no llegaba a hosts reales (.10+).
    import random
    from concurrent.futures import ThreadPoolExecutor

    targets = [(str(ip), p) for net in cfg["targets_subnets"]
               for ip in ipaddress.IPv4Network(net).hosts() for p in ports]

    def probe(t):
        if time.time() >= end:
            return
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(float(cfg.get("connect_timeout", 0.3)))
        try:
            s.connect(t)
        except OSError:
            pass
        finally:
            s.close()

    with ThreadPoolExecutor(max_workers=int(cfg.get("workers", 32))) as ex:
        while time.time() < end:
            random.shuffle(targets)
            list(ex.map(probe, targets))
    return 0
