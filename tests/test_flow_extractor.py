"""Tests para iot/pipeline/flow_extractor.py — usa PCAP sintético."""

from __future__ import annotations

import csv
import socket
import struct
from pathlib import Path

import pytest

from iot.pipeline.flow_extractor import extract


def _write_pcap(path: Path, packets: list[tuple[float, bytes]]) -> None:
    with path.open("wb") as f:
        f.write(struct.pack("<IHHiIII", 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1))
        for ts, data in packets:
            sec = int(ts)
            usec = int((ts - sec) * 1_000_000)
            f.write(struct.pack("<IIII", sec, usec, len(data), len(data)))
            f.write(data)


def _eth_ip_tcp(src_ip: str, dst_ip: str, sport: int, dport: int, flags: int = 0x02, length: int = 60) -> bytes:
    eth = b"\x00" * 12 + b"\x08\x00"
    ip = struct.pack(
        "!BBHHHBBH4s4s",
        0x45, 0, 20 + 20, 1, 0, 64, 6, 0,
        socket.inet_aton(src_ip), socket.inet_aton(dst_ip),
    )
    tcp = struct.pack("!HHLLBBHHH", sport, dport, 0, 0, (5 << 4), flags, 8192, 0, 0)
    pkt = eth + ip + tcp
    if len(pkt) < length:
        pkt += b"\x00" * (length - len(pkt))
    return pkt


def test_extract_one_flow(tmp_path: Path):
    pcap = tmp_path / "tiny.pcap"
    out = tmp_path / "flows.csv"
    pkts = []
    for i in range(5):
        pkts.append((100.0 + i * 0.1, _eth_ip_tcp("10.10.1.10", "10.10.0.12", 5000, 80, flags=0x02)))
    _write_pcap(pcap, pkts)
    n = extract(pcap, out)
    assert n == 1
    rows = list(csv.DictReader(out.open()))
    assert len(rows) == 1
    r = rows[0]
    assert r["src_ip"] == "10.10.1.10"
    assert r["dst_ip"] == "10.10.0.12"
    assert int(r["tot_pkts"]) == 5
    assert int(r["syn_count"]) == 5


def test_extract_protocol_indicators(tmp_path: Path):
    pcap = tmp_path / "p.pcap"
    out = tmp_path / "f.csv"
    pkts = [
        (200.0, _eth_ip_tcp("10.10.1.10", "10.10.0.10", 5000, 1883, flags=0x18)),  # MQTT
        (200.5, _eth_ip_tcp("10.10.2.11", "10.10.0.12", 6000, 502,  flags=0x18)),  # Modbus
    ]
    _write_pcap(pcap, pkts)
    extract(pcap, out)
    rows = list(csv.DictReader(out.open()))
    assert any(int(r["is_mqtt"]) == 1 for r in rows)
    assert any(int(r["is_modbus"]) == 1 for r in rows)
