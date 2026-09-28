#!/usr/bin/env python3
"""Servidor NTP simplificado (responde modo 4, paquete fijo 48 bytes)."""

from __future__ import annotations

import socket
import struct
import sys
import time


def build_response(query: bytes) -> bytes:
    if len(query) < 48:
        return b""
    li_vn_mode = (0 << 6) | (4 << 3) | 4  # LI=0, VN=4, mode=server(4)
    stratum = 2
    poll = 4
    precision = 0xEC
    root_delay = 0
    root_disp = 0
    ref_id = b"LOCL"
    now = time.time() + 2208988800  # NTP epoch
    secs = int(now)
    frac = int((now - secs) * (1 << 32))
    timestamp = struct.pack(">II", secs, frac)
    return (
        bytes([li_vn_mode, stratum, poll, precision])
        + struct.pack(">II", root_delay, root_disp)
        + ref_id
        + timestamp  # ref
        + query[24:32]  # orig from client
        + timestamp  # rx
        + timestamp  # tx
    )


def main() -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", 123))
    print("ntp_server listening on 0.0.0.0:123", flush=True)
    while True:
        try:
            data, addr = s.recvfrom(1024)
        except OSError:
            continue
        resp = build_response(data)
        if resp:
            try:
                s.sendto(resp, addr)
            except OSError:
                pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
