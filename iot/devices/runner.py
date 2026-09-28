#!/usr/bin/env python3
"""
Runner único de dispositivo IoT. Lo lanza mn_iot_topo.py por host.

Implementa con stdlib pura (sin paho/aiocoap) emisores para:
  - mqtt-pub      → frame MQTT 3.1.1 PUBLISH crudo a TCP/1883
  - udp-stream    → ráfaga UDP de tamaño fijo (cámaras, ECG)
  - http-poll     → GET HTTP/1.1 a TCP/80
  - http-post     → POST con JSON a TCP/80
  - coap          → CoAP CON GET (UDP/5683)
  - tcp-modbus    → frame Modbus/TCP read-holding-registers a TCP/502

Resolve `--dst-name` contra mapping fijo de servidores en zona infra
(10.10.0.10..15) sin DNS — los hosts Mininet no tienen resolver.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import socket
import struct
import sys
import time
import uuid


def _sleep_interval(rate: float) -> float:
    """Intervalo con jitter para evitar tráfico perfectamente periódico.

    Sustituye al `period` fijo: introduce variabilidad log-normal alrededor
    del periodo nominal y micro-pausas ocasionales (dispositivo inactivo),
    de modo que las características de tiempo entre llegadas (iat_std, etc.)
    del tráfico benigno dejen de ser triviales de separar.
    """
    period = 1.0 / max(rate, 0.001)
    if random.random() < 0.05:            # ~5% de micro-pausa
        return period * random.uniform(3.0, 8.0)
    return max(0.0005, random.lognormvariate(math.log(period), 0.4))


def _vary_payload(base: int) -> int:
    """Tamaño de payload con variación +/-40% para romper el tamaño fijo."""
    return max(8, int(base * random.uniform(0.6, 1.4)))

SERVERS = {
    "mqtt_broker": ("10.10.0.10", 1883),
    "coap_server": ("10.10.0.11", 5683),
    "http_server": ("10.10.0.12", 80),
    "dns_server":  ("10.10.0.13", 53),
    "ntp_server":  ("10.10.0.14", 123),
    "ssdp_server": ("10.10.0.15", 1900),
}


# ─── Emisores por protocolo ────────────────────────────────────────

def loop_mqtt_pub(args) -> None:
    ip, port = SERVERS["mqtt_broker"]
    topic = f"iot/{args.zone}/{args.name}".encode()
    client_id = f"{args.name}-{uuid.uuid4().hex[:6]}".encode()
    period = 1.0 / max(args.rate, 0.001)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    try:
        sock.connect((ip, port))
        sock.sendall(_mqtt_connect(client_id))
        _read_remaining(sock, 4)  # CONNACK
    except OSError as e:
        print(f"[{args.name}] MQTT connect fallo: {e}", file=sys.stderr)
        return
    seq = 0
    while True:
        payload = json.dumps(
            {"seq": seq, "ts": time.time(), "data": "x" * max(_vary_payload(args.payload) - 60, 8)}
        ).encode()
        try:
            sock.sendall(_mqtt_publish(topic, payload))
        except OSError:
            return
        seq += 1
        time.sleep(_sleep_interval(args.rate))


def loop_udp_stream(args) -> None:
    ip, port = SERVERS[args.dst_name]
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    while True:
        blob = bytes(_vary_payload(args.payload))
        try:
            sock.sendto(blob, (ip, port))
        except OSError:
            time.sleep(0.5)
        time.sleep(_sleep_interval(args.rate))


def loop_http_poll(args) -> None:
    ip, port = SERVERS[args.dst_name]
    period = 1.0 / max(args.rate, 0.001)
    req = (
        f"GET /{args.name} HTTP/1.1\r\n"
        f"Host: {ip}\r\n"
        f"User-Agent: iot-{args.zone}-{args.name}\r\n"
        f"Connection: close\r\n\r\n"
    ).encode()
    while True:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        try:
            s.connect((ip, port))
            s.sendall(req)
            s.recv(args.payload)
        except OSError:
            pass
        finally:
            s.close()
        time.sleep(_sleep_interval(args.rate))


def loop_http_post(args) -> None:
    ip, port = SERVERS[args.dst_name]
    period = 1.0 / max(args.rate, 0.001)
    seq = 0
    while True:
        body = json.dumps(
            {"name": args.name, "zone": args.zone, "seq": seq, "ts": time.time(),
             "pad": "x" * max(_vary_payload(args.payload) - 80, 8)}
        ).encode()
        req = (
            f"POST /telemetry HTTP/1.1\r\nHost: {ip}\r\n"
            f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode() + body
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        try:
            s.connect((ip, port))
            s.sendall(req)
            s.recv(256)
        except OSError:
            pass
        finally:
            s.close()
        seq += 1
        time.sleep(_sleep_interval(args.rate))


def loop_coap(args) -> None:
    ip, port = SERVERS["coap_server"]
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2)
    period = 1.0 / max(args.rate, 0.001)
    mid = random.randint(0, 0xFFFF)
    while True:
        token = random.randint(0, 255)
        path = f"sensors/{args.zone}/{args.name}".encode()
        frame = _coap_get(mid, token, path)
        try:
            sock.sendto(frame, (ip, port))
            sock.recv(args.payload)
        except OSError:
            pass
        mid = (mid + 1) & 0xFFFF
        time.sleep(_sleep_interval(args.rate))


def loop_tcp_modbus(args) -> None:
    ip, port = SERVERS[args.dst_name]
    period = 1.0 / max(args.rate, 0.001)
    tid = 0
    while True:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        try:
            s.connect((ip, port))
            s.sendall(_modbus_read_holding(tid, start=0, count=10))
            s.recv(64)
        except OSError:
            pass
        finally:
            s.close()
        tid = (tid + 1) & 0xFFFF
        time.sleep(_sleep_interval(args.rate))


# ─── MQTT 3.1.1 frames mínimos ────────────────────────────────────

def _mqtt_connect(client_id: bytes) -> bytes:
    proto = b"\x00\x04MQTT"
    flags = 0x02
    keepalive = 60
    var_header = proto + b"\x04" + bytes([flags]) + struct.pack(">H", keepalive)
    payload = struct.pack(">H", len(client_id)) + client_id
    rem = var_header + payload
    return bytes([0x10]) + _mqtt_remaining_len(len(rem)) + rem


def _mqtt_publish(topic: bytes, payload: bytes) -> bytes:
    var_header = struct.pack(">H", len(topic)) + topic
    rem = var_header + payload
    return bytes([0x30]) + _mqtt_remaining_len(len(rem)) + rem


def _mqtt_remaining_len(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _read_remaining(sock: socket.socket, n: int) -> bytes:
    buf = b""
    sock.settimeout(2)
    while len(buf) < n:
        try:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                return buf
            buf += chunk
        except OSError:
            return buf
    return buf


# ─── CoAP frame (RFC 7252) ────────────────────────────────────────

def _coap_get(mid: int, token: int, path: bytes) -> bytes:
    # Ver: 01, Type: CON (00), TKL: 1, Code: 0.01 (GET)
    hdr = bytes([0b01_00_0001, 0x01]) + struct.pack(">H", mid) + bytes([token])
    # Option 11 (Uri-Path): split por '/'
    opts = b""
    prev_num = 0
    for part in path.split(b"/"):
        if not part:
            continue
        delta = 11 - prev_num
        prev_num = 11
        if len(part) < 13:
            opts += bytes([(delta << 4) | len(part)]) + part
        else:
            opts += bytes([(delta << 4) | 13, len(part) - 13]) + part
    return hdr + opts


# ─── Modbus/TCP ───────────────────────────────────────────────────

def _modbus_read_holding(tid: int, start: int, count: int) -> bytes:
    pdu = bytes([0x03]) + struct.pack(">HH", start, count)
    mbap = struct.pack(">HHHB", tid, 0, len(pdu) + 1, 1)
    return mbap + pdu


# ─── Main ─────────────────────────────────────────────────────────

DISPATCH = {
    "mqtt-pub":   loop_mqtt_pub,
    "udp-stream": loop_udp_stream,
    "http-poll":  loop_http_poll,
    "http-post":  loop_http_post,
    "coap":       loop_coap,
    "tcp-modbus": loop_tcp_modbus,
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--proto", required=True, choices=list(DISPATCH))
    p.add_argument("--dst-name", required=True)
    p.add_argument("--rate", type=float, required=True, help="paquetes por segundo")
    p.add_argument("--payload", type=int, default=200, help="bytes por paquete")
    p.add_argument("--zone", default="unknown")
    args = p.parse_args()

    # jitter inicial para no sincronizar todos los hosts
    time.sleep(random.uniform(0, 2.0))
    DISPATCH[args.proto](args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
