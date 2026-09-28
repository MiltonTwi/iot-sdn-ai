#!/usr/bin/env python3
"""Smoke test offline de los escenarios de ataque reforzados.

Valida SIN VM: (1) todos los módulos importan, (2) los builders de paquetes
producen bytes correctos y tuplas variadas, (3) udp_flood rota source ports de
verdad contra un receptor loopback. Los paths raw-socket (icmp/amp/mirai run())
sólo corren con root en Linux; aquí validamos su lógica de construcción.
"""
from __future__ import annotations

import socket
import struct
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAIL = []


def check(name, cond, detail=""):
    tag = "OK  " if cond else "FAIL"
    if not cond:
        FAIL.append(name)
    print(f"  [{tag}] {name} {detail}")


# 1) imports
from iot.attacks.scenarios import (  # noqa: E402
    udp_flood, icmp_flood, dns_amplification, coap_amplification,
    ssdp_amplification, credential_bruteforce, mirai_coordinated,
)
print("1) imports")
check("import 7 escenarios reforzados", True)

# 2) builders de paquetes
print("2) builders de paquetes")

# amplificacion: _victim_pool y _ip/_udp
vp = dns_amplification._victim_pool("10.10.1.10", 254)
check("dns _victim_pool 254 IPs distintas", len(set(vp)) == 254, f"({len(set(vp))})")
check("dns _victim_pool respeta /24", vp[0] == "10.10.1.1" and vp[-1] == "10.10.1.254")
ip = dns_amplification._ip("10.10.1.5", "10.10.0.13", 20)
check("dns _ip len=20 header", len(ip) == 20)
check("dns _ip total_len campo", struct.unpack("!H", ip[2:4])[0] == 40)

for mod, name in ((coap_amplification, "coap"), (ssdp_amplification, "ssdp")):
    p = mod._victim_pool("10.10.4.16", 254)
    check(f"{name} _victim_pool 254 distintas", len(set(p)) == 254)

# icmp: checksum, echo, src_pool
echo = icmp_flood._icmp_echo()
check("icmp echo type=8", echo[0] == 8)
# checksum valido → recomputar sobre el paquete da 0
check("icmp checksum correcto", icmp_flood._checksum(echo) == 0, f"(={icmp_flood._checksum(echo)})")
sp = icmp_flood._src_pool("10.10.1.100", 256)
check("icmp _src_pool sin duplicados en rango", len(set(sp)) == len(sp), f"({len(set(sp))})")

# mirai: TCP SYN checksum + flags
seg = mirai_coordinated._tcp_syn("10.10.1.50", "10.10.0.12", 40000, 80)
check("mirai TCP header 20 bytes", len(seg) == 20)
flags = struct.unpack("!H", seg[12:14])[0] & 0x3F
check("mirai flag SYN set", flags == 0x02, f"(flags={flags:#04x})")
bp = mirai_coordinated._bot_pool("10.10.1.50", 64)
check("mirai _bot_pool 64 IPs", len(bp) == 64)

# 3) udp_flood rota sports de verdad (loopback)
print("3) udp_flood rotacion real de source ports")
rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
rx.bind(("127.0.0.1", 0))
rx_port = rx.getsockname()[1]
seen_sports = set()
stop = threading.Event()


def receiver():
    rx.settimeout(0.2)
    while not stop.is_set():
        try:
            _, addr = rx.recvfrom(2048)
            seen_sports.add(addr[1])
        except socket.timeout:
            pass
        except OSError:
            break


t = threading.Thread(target=receiver, daemon=True)
t.start()
rc = udp_flood.run({"target_ip": "127.0.0.1", "target_port": rx_port,
                    "duration_s": 1.0, "src_ports": 64})
time.sleep(0.3)
stop.set()
t.join(timeout=1)
rx.close()
check("udp_flood rc=0", rc == 0)
check("udp_flood usa multiples source ports", len(seen_sports) >= 20,
      f"(sports distintos vistos={len(seen_sports)})")

print()
if FAIL:
    print(f"RESULTADO: {len(FAIL)} FALLO(S) → {FAIL}")
    sys.exit(1)
print("RESULTADO: TODO OK (validacion offline; raw-socket run() requiere VM+root)")
