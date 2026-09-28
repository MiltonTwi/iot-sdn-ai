#!/usr/bin/env python3
"""Servidor CoAP mínimo. Responde 2.05 Content a cualquier GET CON."""

from __future__ import annotations

import socket
import struct
import sys


def main() -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", 5683))
    print("coap_server listening on 0.0.0.0:5683", flush=True)
    while True:
        try:
            data, addr = s.recvfrom(4096)
        except OSError:
            continue
        if len(data) < 4:
            continue
        ver_t_tkl = data[0]
        tkl = ver_t_tkl & 0x0F
        # Respuesta ACK + 2.05 Content (0x45)
        mid = data[2:4]
        token = data[4 : 4 + tkl]
        # Type=ACK (10), TKL=tkl, code=2.05 (0x45)
        hdr = bytes([0b01_10_0000 | tkl, 0x45]) + mid + token
        payload_marker = b"\xff"
        body = b'{"ok":true}'
        try:
            s.sendto(hdr + payload_marker + body, addr)
        except OSError:
            pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
