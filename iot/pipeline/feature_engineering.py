#!/usr/bin/env python3
"""
Feature engineering posterior al extractor — agregaciones en ventanas de 5s.

Dos familias de agregados:
  - host_*  : por src_ip  (comportamiento del emisor)
  - dst_*   : por dst_ip  (comportamiento del receptor / reflector)

Las dst_* son clave para amplificación/reflexión: un reflector bajo ataque
recibe muchos src distintos concentrados en un dst+puerto en poco tiempo, señal
invisible para las features por-source cuando el atacante spoofea/rota orígenes.

Implementación STREAMING (memoria acotada): ordena por start_ts con `sort`
externo (merge en disco) y recorre una sola vez manteniendo, por src_ip y por
dst_ip, una ventana deslizante de 5s con agregados incrementales. Evita el
O(n^2)/OOM de cargar 2.9M filas en memoria.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import tempfile
from collections import defaultdict, deque
from pathlib import Path

WINDOW_S = 5.0


class SrcWin:
    """Ventana deslizante 5s por src con agregados incrementales."""
    __slots__ = ("dq", "pkts", "bytes", "syn", "dst", "dport")

    def __init__(self) -> None:
        self.dq: deque = deque()
        self.pkts = 0
        self.bytes = 0
        self.syn = 0
        self.dst: dict[str, int] = defaultdict(int)
        self.dport: dict[str, int] = defaultdict(int)

    def prune(self, ts: float) -> None:
        while self.dq and ts - self.dq[0][0] > WINDOW_S:
            _ts, d, dp, pk, by, sy = self.dq.popleft()
            self.pkts -= pk
            self.bytes -= by
            self.syn -= sy
            if self.dst[d] <= 1:
                del self.dst[d]
            else:
                self.dst[d] -= 1
            if self.dport[dp] <= 1:
                del self.dport[dp]
            else:
                self.dport[dp] -= 1

    def add(self, ts: float, d: str, dp: str, pk: int, by: int, sy: int) -> None:
        self.dq.append((ts, d, dp, pk, by, sy))
        self.pkts += pk
        self.bytes += by
        self.syn += sy
        self.dst[d] += 1
        self.dport[dp] += 1


class DstWin:
    """Ventana deslizante 5s por dst — mide concentración de orígenes (reflexión)."""
    __slots__ = ("dq", "pkts", "bytes", "src")

    def __init__(self) -> None:
        self.dq: deque = deque()
        self.pkts = 0
        self.bytes = 0
        self.src: dict[str, int] = defaultdict(int)

    def prune(self, ts: float) -> None:
        while self.dq and ts - self.dq[0][0] > WINDOW_S:
            _ts, s, pk, by = self.dq.popleft()
            self.pkts -= pk
            self.bytes -= by
            if self.src[s] <= 1:
                del self.src[s]
            else:
                self.src[s] -= 1

    def add(self, ts: float, s: str, pk: int, by: int) -> None:
        self.dq.append((ts, s, pk, by))
        self.pkts += pk
        self.bytes += by
        self.src[s] += 1


def _sorted_by_start_ts(inp: Path) -> tuple[Path, list[str]]:
    """Escribe un temp ordenado por start_ts (numerico). Devuelve (path, header)."""
    with inp.open(encoding="utf-8") as f:
        header = f.readline().rstrip("\n")
    cols = header.split(",")
    idx = cols.index("start_ts") + 1  # 1-based para sort -k
    tmp = Path(tempfile.mkstemp(suffix=".csv", prefix="feat_sort_")[1])
    with tmp.open("w", encoding="utf-8") as out:
        out.write(header + "\n")
        out.flush()  # sin esto `sort` escribe al fd antes que el buffer → header al final
        p1 = subprocess.Popen(["tail", "-n", "+2", str(inp)], stdout=subprocess.PIPE)
        p2 = subprocess.Popen(
            ["sort", "-t,", f"-k{idx},{idx}g", "-S", "400M"],
            stdin=p1.stdout, stdout=out,
        )
        p1.stdout.close()
        p2.communicate()
        p1.wait()
    return tmp, cols


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--inp", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    tmp, cols = _sorted_by_start_ts(args.inp)
    ci = {c: i for i, c in enumerate(cols)}
    extra = [
        "host_flows_5s", "host_distinct_dst_5s", "host_distinct_dport_5s",
        "host_pkts_5s", "host_bytes_5s", "host_syn_5s", "host_syn_ratio",
        "dst_flows_5s", "dst_distinct_src_5s", "dst_pkts_5s", "dst_bytes_5s",
    ]

    wins: dict[str, SrcWin] = defaultdict(SrcWin)
    dwins: dict[str, DstWin] = defaultdict(DstWin)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    try:
        with tmp.open(encoding="utf-8") as inf, args.out.open("w", newline="", encoding="utf-8") as outf:
            r = csv.reader(inf)
            w = csv.writer(outf)
            next(r)  # header
            w.writerow(cols + extra)
            for row in r:
                if len(row) < len(cols):
                    continue
                src = row[ci["src_ip"]]
                dst = row[ci["dst_ip"]]
                ts = float(row[ci["start_ts"]])
                win = wins[src]
                win.prune(ts)
                dwin = dwins[dst]
                dwin.prune(ts)
                # stats sobre flujos previos dentro de la ventana (sin incluir el actual)
                hp = win.pkts
                hf = len(win.dq)
                row_out = row + [
                    hf,
                    len(win.dst),
                    len(win.dport),
                    hp,
                    win.bytes,
                    win.syn,
                    (win.syn / hp) if hp else 0.0,
                    len(dwin.dq),
                    len(dwin.src),
                    dwin.pkts,
                    dwin.bytes,
                ]
                w.writerow(row_out)
                # agrega el flujo actual a las ventanas de su src y su dst
                pk = int(row[ci["tot_pkts"]])
                by = int(row[ci["tot_bytes"]])
                win.add(ts, dst, row[ci["dst_port"]], pk, by, int(row[ci["syn_count"]]))
                dwin.add(ts, src, pk, by)
                n += 1
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass

    print(f"Feature-engineered (streaming) → {args.out} ({n} filas)")


if __name__ == "__main__":
    main()
