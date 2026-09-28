#!/usr/bin/env python3
"""Broker MQTT 3.1.1 mínimo (lee CONNECT/PUBLISH, responde CONNACK)."""

from __future__ import annotations

import socket
import struct
import sys
import threading


def handle(conn: socket.socket) -> None:
    try:
        # CONNECT esperado primero
        if not _read_packet(conn):
            return
        conn.sendall(bytes([0x20, 0x02, 0x00, 0x00]))  # CONNACK accepted
        while True:
            if not _read_packet(conn):
                return
    except OSError:
        return
    finally:
        conn.close()


def _read_packet(conn: socket.socket) -> bool:
    h = conn.recv(1)
    if not h:
        return False
    rem = 0
    mult = 1
    for _ in range(4):
        b = conn.recv(1)
        if not b:
            return False
        rem += (b[0] & 0x7F) * mult
        if not (b[0] & 0x80):
            break
        mult *= 128
    body = b""
    while len(body) < rem:
        chunk = conn.recv(rem - len(body))
        if not chunk:
            return False
        body += chunk
    return True


def main() -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", 1883))
    s.listen(64)
    print("mqtt_broker listening on 0.0.0.0:1883", flush=True)
    while True:
        conn, _ = s.accept()
        threading.Thread(target=handle, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
