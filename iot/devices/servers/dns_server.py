#!/usr/bin/env python3
"""DNS UDP mínimo. Responde A=10.10.0.12 a cualquier query.

Responde con paquetes grandes intencionalmente (TXT relleno) para que el
ataque DNS-amplification tenga factor de amplificación visible.
"""

from __future__ import annotations

import socket
import struct
import sys


def build_response(query: bytes) -> bytes:
    if len(query) < 12:
        return b""
    txid = query[:2]
    qd = query[12:]
    # encontrar fin del QNAME
    i = 0
    while i < len(qd) and qd[i] != 0:
        i += 1 + qd[i]
    if i >= len(qd):
        return b""
    qname = qd[: i + 1]
    qtype_class = qd[i + 1 : i + 5]
    flags = b"\x81\x80"
    counts = struct.pack(">HHHH", 1, 1, 0, 0)
    answer = (
        b"\xc0\x0c"           # name pointer
        + b"\x00\x10"         # type TXT
        + b"\x00\x01"         # class IN
        + b"\x00\x00\x00\x3c" # TTL 60
        + struct.pack(">H", 256)  # rdlength relleno (amplificación)
        + bytes([255]) + (b"A" * 255)
    )
    return txid + flags + counts + qname + qtype_class + answer


def main() -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", 53))
    print("dns_server listening on 0.0.0.0:53", flush=True)
    while True:
        try:
            data, addr = s.recvfrom(2048)
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
