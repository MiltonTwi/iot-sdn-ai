#!/usr/bin/env python3
"""
PCAP → flow records (CSV).

Construye flujos bidireccionales por 5-tupla (src, sport, dst, dport, proto)
con timeout de inactividad. Compatible con scapy y con dpkt; si ninguno está,
usa parser de stdlib mínimo (Ethernet/IPv4/TCP/UDP/ICMP).

Sale: features estilo CICFlowMeter reducidas (38 columnas).
"""

from __future__ import annotations

import argparse
import csv
import math
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

FLOW_TIMEOUT = 60.0


@dataclass(slots=True)
class FlowState:
    """Agregados INCREMENTALES (no listas): un pcap con floods tiene millones de
    flujos concurrentes; guardar cada timestamp/length por flujo desbordaba la
    RAM (OOM a 2.7 GB con pcap de 9 GB). Aquí cada flujo ocupa O(1): sumas,
    sumas de cuadrados, min/max e histograma de longitudes acotado."""
    src: str
    dst: str
    sport: int
    dport: int
    proto: int
    fwd_pkts: int = 0
    bwd_pkts: int = 0
    fwd_bytes: int = 0
    bwd_bytes: int = 0
    # longitudes por dirección: sum, sum de cuadrados, max, min
    fwd_len_sum: int = 0
    fwd_len_sq: float = 0.0
    fwd_len_max: int = 0
    fwd_len_min: int = 0
    bwd_len_sum: int = 0
    bwd_len_sq: float = 0.0
    bwd_len_max: int = 0
    bwd_len_min: int = 0
    # IAT global (entre paquetes consecutivos de cualquier dirección)
    iat_n: int = 0
    iat_sum: float = 0.0
    iat_sq: float = 0.0
    iat_max: float = 0.0
    iat_min: float = 0.0
    # IAT por dirección (solo media → basta count + sum)
    fwd_iat_n: int = 0
    fwd_iat_sum: float = 0.0
    bwd_iat_n: int = 0
    bwd_iat_sum: float = 0.0
    last_fwd_ts: float = 0.0
    last_bwd_ts: float = 0.0
    # histograma de longitudes (bucket //50) para entropía — acotado (~30 claves)
    len_hist: dict = field(default_factory=dict)
    syn: int = 0
    fin: int = 0
    rst: int = 0
    psh: int = 0
    ack: int = 0
    urg: int = 0
    start_ts: float = 0.0
    last_ts: float = 0.0


COLUMNS = [
    "src_ip", "dst_ip", "src_port", "dst_port", "proto",
    "start_ts", "duration",
    "tot_fwd_pkts", "tot_bwd_pkts", "tot_pkts",
    "tot_fwd_bytes", "tot_bwd_bytes", "tot_bytes",
    "fwd_pkt_len_mean", "fwd_pkt_len_std", "fwd_pkt_len_max", "fwd_pkt_len_min",
    "bwd_pkt_len_mean", "bwd_pkt_len_std", "bwd_pkt_len_max", "bwd_pkt_len_min",
    "iat_mean", "iat_std", "iat_max", "iat_min",
    "fwd_iat_mean", "bwd_iat_mean",
    "syn_count", "fin_count", "rst_count", "psh_count", "ack_count", "urg_count",
    "fwd_pps", "bwd_pps",
    "down_up_ratio", "byte_entropy",
    "is_mqtt", "is_coap", "is_modbus", "is_dns", "is_ntp", "is_ssdp", "is_http",
]


def _mean_std(n, s, sq):
    """media y desviación poblacional desde count/sum/sum-of-squares."""
    if n <= 0:
        return 0.0, 0.0
    mean = s / n
    if n == 1:
        return mean, 0.0
    var = max(sq / n - mean * mean, 0.0)  # clamp por error de redondeo
    return mean, math.sqrt(var)


def feats(f: FlowState) -> dict:
    duration = max(f.last_ts - f.start_ts, 1e-6)
    fwd_mean, fwd_std = _mean_std(f.fwd_pkts, f.fwd_len_sum, f.fwd_len_sq)
    bwd_mean, bwd_std = _mean_std(f.bwd_pkts, f.bwd_len_sum, f.bwd_len_sq)
    iat_mean, iat_std = _mean_std(f.iat_n, f.iat_sum, f.iat_sq)

    tot_pkts = f.fwd_pkts + f.bwd_pkts
    tot_bytes = f.fwd_bytes + f.bwd_bytes
    down_up = (f.bwd_bytes / f.fwd_bytes) if f.fwd_bytes else 0.0
    return {
        "src_ip": f.src, "dst_ip": f.dst,
        "src_port": f.sport, "dst_port": f.dport, "proto": f.proto,
        "start_ts": f.start_ts, "duration": duration,
        "tot_fwd_pkts": f.fwd_pkts, "tot_bwd_pkts": f.bwd_pkts, "tot_pkts": tot_pkts,
        "tot_fwd_bytes": f.fwd_bytes, "tot_bwd_bytes": f.bwd_bytes, "tot_bytes": tot_bytes,
        "fwd_pkt_len_mean": fwd_mean, "fwd_pkt_len_std": fwd_std,
        "fwd_pkt_len_max": f.fwd_len_max, "fwd_pkt_len_min": f.fwd_len_min,
        "bwd_pkt_len_mean": bwd_mean, "bwd_pkt_len_std": bwd_std,
        "bwd_pkt_len_max": f.bwd_len_max, "bwd_pkt_len_min": f.bwd_len_min,
        "iat_mean": iat_mean, "iat_std": iat_std,
        "iat_max": f.iat_max, "iat_min": (f.iat_min if f.iat_n else 0.0),
        "fwd_iat_mean": (f.fwd_iat_sum / f.fwd_iat_n if f.fwd_iat_n else 0.0),
        "bwd_iat_mean": (f.bwd_iat_sum / f.bwd_iat_n if f.bwd_iat_n else 0.0),
        "syn_count": f.syn, "fin_count": f.fin, "rst_count": f.rst,
        "psh_count": f.psh, "ack_count": f.ack, "urg_count": f.urg,
        "fwd_pps": f.fwd_pkts / duration, "bwd_pps": f.bwd_pkts / duration,
        "down_up_ratio": down_up,
        "byte_entropy": _entropy_hist(f.len_hist),
        "is_mqtt":   int(f.dport == 1883 or f.sport == 1883),
        "is_coap":   int(f.dport == 5683 or f.sport == 5683),
        "is_modbus": int(f.dport == 502  or f.sport == 502),
        "is_dns":    int(f.dport == 53   or f.sport == 53),
        "is_ntp":    int(f.dport == 123  or f.sport == 123),
        "is_ssdp":   int(f.dport == 1900 or f.sport == 1900),
        "is_http":   int(f.dport == 80   or f.sport == 80),
    }


def _entropy_hist(counts: dict) -> float:
    total = sum(counts.values())
    if not total:
        return 0.0
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


# ─── PCAP parser stdlib (sin scapy/dpkt) ───────────────────────────

def parse_pcap(path):
    """pcap clásico desde una ruta o desde un stream binario ya abierto (stdin en --live)."""
    if not isinstance(path, Path):
        yield from _parse_stream(path)
        return
    with path.open("rb") as f:
        yield from _parse_stream(f)


def _parse_stream(f):
    magic = f.read(4)
    if magic == b"\xd4\xc3\xb2\xa1":
        endian = "<"
    elif magic == b"\xa1\xb2\xc3\xd4":
        endian = ">"
    else:
        raise ValueError(f"Magia PCAP no reconocida: {magic.hex()}")
    rest_hdr = f.read(20)
    linktype = struct.unpack(endian + "I", rest_hdr[16:20])[0]
    if linktype == 113:
        parser = _parse_sll
    elif linktype == 276:
        parser = _parse_sll2
    else:
        parser = _parse_eth
    while True:
        hdr = f.read(16)
        if len(hdr) < 16:
            return
        ts_sec, ts_usec, incl_len, orig_len = struct.unpack(endian + "IIII", hdr)
        ts = ts_sec + ts_usec / 1_000_000
        data = f.read(incl_len)
        if len(data) < incl_len:
            return
        parsed = parser(data)
        if parsed:
            # parser devuelve frame_len = bytes CAPTURADOS; con snaplen (-s N)
            # eso subestima el tamaño real. Usar orig_len (longitud en el cable)
            # para que las features de tamaño sigan siendo correctas.
            src, dst, sport, dport, proto, _caplen, flags = parsed
            yield (ts, src, dst, sport, dport, proto, orig_len, flags)


def _parse_ip(ip: bytes, frame_len: int):
    if len(ip) < 20:
        return None
    vihl = ip[0]
    ihl = (vihl & 0x0F) * 4
    proto = ip[9]
    src = ".".join(map(str, ip[12:16]))
    dst = ".".join(map(str, ip[16:20]))
    rest = ip[ihl:]
    sport = dport = 0
    flags = 0
    if proto == 6 and len(rest) >= 14:
        sport, dport = struct.unpack("!HH", rest[0:4])
        flags = rest[13]
    elif proto == 17 and len(rest) >= 8:
        sport, dport = struct.unpack("!HH", rest[0:4])
    return src, dst, sport, dport, proto, frame_len, flags


def _parse_eth(b: bytes):
    if len(b) < 14:
        return None
    eth_type = struct.unpack("!H", b[12:14])[0]
    if eth_type != 0x0800:
        return None
    return _parse_ip(b[14:], len(b))


def _parse_sll(b: bytes):
    if len(b) < 16:
        return None
    proto = struct.unpack("!H", b[14:16])[0]
    if proto != 0x0800:
        return None
    return _parse_ip(b[16:], len(b))


def _parse_sll2(b: bytes):
    if len(b) < 20:
        return None
    proto = struct.unpack("!H", b[0:2])[0]
    if proto != 0x0800:
        return None
    return _parse_ip(b[20:], len(b))


SWEEP_EVERY = 2.0       # s de tiempo de captura entre barridos de flujos expirados
MAX_ACTIVE = 300_000    # válvula: si hay más flujos activos, purga los más viejos


def extract(pcap, out: Path | None, *, live_dir: Path | None = None,
            emit_every: float = 5.0, span: float | None = None) -> int:
    """Streaming + agregados O(1) por flujo. Un flujo inactivo > FLOW_TIMEOUT ya
    no puede crecer (el siguiente paquete abre uno nuevo), así que se escribe y
    se libera en barridos periódicos. Memoria = flujos activos, no total del pcap
    (un pcap de 9 GB con floods spoofeados daba OOM al acumularlo todo).
    Válvula MAX_ACTIVE: en un pico de flujos de 1 paquete (SYN spoof) fuerza el
    volcado de los más antiguos aunque no hayan expirado.

    Modo live (`live_dir`): `pcap` es un stream (stdin de `tcpdump -U -w -`) y el
    estado de los flujos persiste entre ventanas. Cada `emit_every` s se escribe
    live_dir/flows_<t>.csv con un snapshot ACUMULADO (desde el inicio del flujo)
    de cada flujo que recibió paquetes en la ventana, más los que expiraron. Así
    una conexión larga (slowloris, MQTT) se ve con su duración real y no
    truncada a la ventana, como en el dataset de entrenamiento.

    `span` (≥ emit_every): el snapshot incluye los flujos con paquetes en los
    últimos `span` s, no solo en la última ventana. Con emit_every=2 y span=5 se
    decide cada 2 s pero las agregaciones host_*_5s / dst_*_5s ven 5 s de
    actividad, igual que en entrenamiento (con span=2 los ataques de baja tasa
    quedaban por debajo del umbral)."""
    span = max(span or emit_every, emit_every)
    flows: dict[tuple, FlowState] = {}
    last_seen: dict[tuple, float] = {}
    touched: dict[tuple, float] = {}  # flujo → ts de su último paquete (live)
    n_flows = 0
    next_sweep = None
    next_emit = None
    win_start = 0.0

    def open_writer(path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = path.open("w", newline="", encoding="utf-8")
        wr = csv.DictWriter(fh, fieldnames=COLUMNS)
        wr.writeheader()
        return fh, wr

    tmp = live_dir / ".flows.tmp" if live_dir else None
    fp, w = open_writer(tmp if live_dir else out)

    def emit(f: FlowState) -> None:
        nonlocal n_flows
        n_flows += 1
        if live_dir is None:  # en live el flujo ya salió en los snapshots de sus ventanas
            w.writerow(feats(f))

    def emit_window(now: float) -> None:
        """Cierra la ventana live: snapshot de los flujos con paquetes en los
        últimos `span` s → archivo final."""
        nonlocal fp, w
        for k in [k for k, t in touched.items() if now - t > span]:
            del touched[k]
        for k in touched:
            f = flows.get(k)
            if f is not None:
                w.writerow(feats(f))
        fp.close()
        tmp.rename(live_dir / f"flows_{int(win_start)}.csv")
        fp, w = open_writer(tmp)

    def sweep(now: float) -> None:
        dead = [k for k, t in last_seen.items() if now - t > FLOW_TIMEOUT]
        for k in dead:
            emit(flows.pop(k))
            del last_seen[k]
        # válvula de seguridad: si aún hay demasiados activos, vuelca los más
        # antiguos por last_seen (flood de flujos de 1 paquete que no expiran aún)
        if len(flows) > MAX_ACTIVE:
            oldest = sorted(last_seen.items(), key=lambda kv: kv[1])[: len(flows) - MAX_ACTIVE]
            for k, _ in oldest:
                emit(flows.pop(k))
                del last_seen[k]

    def key(src, sport, dst, dport, proto, ts):
        a = (src, sport)
        b = (dst, dport)
        # TCP tiene SYN/FIN que delimitan sesiones naturalmente.
        # UDP/ICMP no — un flood de 30s con mismo 5-tuple colapsa a 1 flow.
        # Bucket por ventanas de 2s para que un flood produzca ~N/2 flows.
        if proto != 6:
            return (proto, *(min(a, b)), *(max(a, b)), int(ts / 2.0))
        return (proto, *(min(a, b)), *(max(a, b)))

    n = 0
    for ts, src, dst, sport, dport, proto, length, flags in parse_pcap(pcap):
        if next_sweep is None:
            next_sweep = ts + SWEEP_EVERY
        elif ts >= next_sweep:
            sweep(ts)
            next_sweep = ts + SWEEP_EVERY
        if live_dir is not None:
            if next_emit is None:
                win_start, next_emit = ts, ts + emit_every
            elif ts >= next_emit:
                emit_window(ts)
                win_start, next_emit = ts, ts + emit_every
        k = key(src, sport, dst, dport, proto, ts)
        if live_dir is not None:  # en batch no: crecería con todo el pcap
            touched[k] = ts
        f = flows.get(k)
        if f is None or ts - last_seen.get(k, ts) > FLOW_TIMEOUT:
            if f is not None:
                emit(f)
            f = FlowState(src=src, dst=dst, sport=sport, dport=dport, proto=proto, start_ts=ts)
            flows[k] = f
        # IAT global (respecto al último paquete de cualquier dirección)
        if f.last_ts:
            d = ts - f.last_ts
            if f.iat_n == 0 or d < f.iat_min:
                f.iat_min = d
            if d > f.iat_max:
                f.iat_max = d
            f.iat_n += 1
            f.iat_sum += d
            f.iat_sq += d * d
        last_seen[k] = ts
        f.last_ts = ts
        f.len_hist[length // 50] = f.len_hist.get(length // 50, 0) + 1
        is_fwd = (src, sport) == (f.src, f.sport)
        if is_fwd:
            f.fwd_pkts += 1
            f.fwd_bytes += length
            f.fwd_len_sum += length
            f.fwd_len_sq += length * length
            if length > f.fwd_len_max:
                f.fwd_len_max = length
            if f.fwd_pkts == 1 or length < f.fwd_len_min:
                f.fwd_len_min = length
            if f.last_fwd_ts:
                f.fwd_iat_n += 1
                f.fwd_iat_sum += ts - f.last_fwd_ts
            f.last_fwd_ts = ts
        else:
            f.bwd_pkts += 1
            f.bwd_bytes += length
            f.bwd_len_sum += length
            f.bwd_len_sq += length * length
            if length > f.bwd_len_max:
                f.bwd_len_max = length
            if f.bwd_pkts == 1 or length < f.bwd_len_min:
                f.bwd_len_min = length
            if f.last_bwd_ts:
                f.bwd_iat_n += 1
                f.bwd_iat_sum += ts - f.last_bwd_ts
            f.last_bwd_ts = ts
        if proto == 6:
            f.syn += int(bool(flags & 0x02))
            f.fin += int(bool(flags & 0x01))
            f.rst += int(bool(flags & 0x04))
            f.psh += int(bool(flags & 0x08))
            f.ack += int(bool(flags & 0x10))
            f.urg += int(bool(flags & 0x20))
        n += 1

    for f in flows.values():
        emit(f)
    fp.close()
    print(f"Procesados {n} paquetes → {n_flows} flujos en {out}")
    return n_flows


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--pcap", type=Path)
    p.add_argument("--out", type=Path)
    p.add_argument("--live-dir", type=Path,
                   help="modo live: lee pcap de stdin y emite snapshots por ventana aquí")
    p.add_argument("--emit-every", type=float, default=5.0)
    p.add_argument("--span", type=float, default=None,
                   help="live: el snapshot cubre los flujos activos en los últimos SPAN s")
    args = p.parse_args()
    if args.live_dir:
        extract(sys.stdin.buffer, None, live_dir=args.live_dir, emit_every=args.emit_every,
                span=args.span)
        return
    if not args.pcap or not args.out:
        p.error("--pcap y --out requeridos (o --live-dir)")
    if not args.pcap.exists():
        print(f"PCAP no existe: {args.pcap}", file=sys.stderr)
        sys.exit(1)
    extract(args.pcap, args.out)


if __name__ == "__main__":
    main()
