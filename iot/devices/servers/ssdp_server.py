#!/usr/bin/env python3
"""SSDP (UPnP) responder — usado para amplificación.

Responde con anuncio largo a M-SEARCH, sirviendo de reflector.
"""

from __future__ import annotations

import socket
import sys


RESPONSE = (
    b"HTTP/1.1 200 OK\r\n"
    b"CACHE-CONTROL: max-age=120\r\n"
    b"DATE: Mon, 04 May 2026 00:00:00 GMT\r\n"
    b"EXT:\r\n"
    b"LOCATION: http://10.10.0.12/desc.xml\r\n"
    b"SERVER: IoTLab/1.0 UPnP/1.0\r\n"
    b"ST: upnp:rootdevice\r\n"
    b"USN: uuid:" + b"a" * 200 + b"::upnp:rootdevice\r\n"
    b"\r\n"
)


def main() -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", 1900))
    print("ssdp_server listening on 0.0.0.0:1900", flush=True)
    while True:
        try:
            data, addr = s.recvfrom(2048)
        except OSError:
            continue
        if b"M-SEARCH" in data[:32]:
            try:
                s.sendto(RESPONSE, addr)
            except OSError:
                pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
