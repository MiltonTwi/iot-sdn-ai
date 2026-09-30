#!/usr/bin/env python3
"""Lazo cerrado en vivo: micro-lotes de flujos → detector 2 etapas → controlador SDN.

Consume los CSV que escribe `iot/pipeline/live_capture.sh` (data/live/feat_<ts>.csv,
uno por chunk de captura) y, por cada chunk:

1. **Detección** (etapa 1): XGB colapsado a P(ataque) con umbral afinado para
   prevalencia baja (`base_rate.json`, XGB @1 %, precision ≥ 0,9). RF no sirve aquí:
   a prevalencia 1 % ningún umbral le da precision ≥ 0,9 (Fase 3).
2. **Atribución** (etapa 2): RF sobre los flujos marcados → clase de ataque.
3. **Agregación**: se actúa por incidente, no por flujo. Un origen es incidente si
   tiene ≥ MIN_FLOWS flujos marcados y son ≥ MIN_FRAC de sus flujos del chunk.
   Un destino con ≥ DIST_SRCS orígenes atacantes distintos = ataque distribuido o
   con origen falsificado → se protege el destino (LIMIT por dst+proto), no se
   persiguen orígenes que pueden ser falsos. La evidencia por origen se acumula
   en los últimos WINDOW_S segundos (ataques de baja tasa).
4. **Política** (match mínimo que contiene el ataque):
   - amplificación: el flujo va víctima(falsificada)→reflector:puerto. LIMIT a ese
     par + puerto (o, si rocía muchas víctimas, a las consultas hacia el
     reflector); nunca DROP del reflector (es un servidor legítimo).
   - floods/botnet, fuerza bruta, abuso de protocolo, baja tasa: DROP del origen
     (los de TCP completan handshake → el origen no está falsificado; un LIMIT
     en kbps no frena frames pequeños: MQTT malformado pasaba igual).
   - recon: LIMIT del origen (menos dañino; puede ser un inventario legítimo).
   - orígenes protegidos (servidores de infraestructura): nunca DROP global;
     se degrada a LIMIT sobre el par (origen, destino).

Cada acción queda en data/live/actions.jsonl con la latencia fin-de-chunk → regla.

  python3 ml_extra/live_detector.py --live-dir data/live --controller http://localhost:8080
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "ml_extra" / "artifacts"

FAMILY = {
    "SYN_FLOOD": "ddos", "UDP_FLOOD": "ddos", "ICMP_FLOOD": "ddos", "HTTP_FLOOD": "ddos",
    "MIRAI_COORDINATED": "ddos",
    "DNS_AMPLIFICATION": "amplification", "COAP_AMPLIFICATION": "amplification",
    "SSDP_AMPLIFICATION": "amplification",
    "PORT_SCAN": "recon", "CREDENTIAL_BRUTEFORCE": "bruteforce",
    "MQTT_SUBSCRIBE_FLOOD": "protocol_abuse", "MQTT_MALFORMED": "protocol_abuse",
    "SLOWLORIS": "dos_low_rate",
}
PROTECTED = {"10.10.0.10", "10.10.0.11", "10.10.0.12", "10.10.0.13", "10.10.0.14", "10.10.0.15"}

MIN_FLOWS = 5
MIN_FRAC = 0.5
DIST_SRCS = 20
LIMIT_KBPS = 512          # LIMIT por origen (recon, fuerza bruta, abuso de protocolo)
LIMIT_KBPS_TIGHT = 64     # destino protegido / amplificación: paquetes pequeños (ICMP
                          # 98 B, consultas DNS ~70 B) → 512 kbps dejaba pasar ~900 pps
SRC_THR = 0.9             # umbral por flujo para la evidencia POR ORIGEN (ver score())
DURATION_S = 60
COOLDOWN_S = 30
MAX_ROWS = 20000
ATTR_MAX = 2000    # flujos marcados que atribuye el RF por chunk; el resto hereda la
                   # etiqueta de su origen/destino (bajo flood el RF sobre 20 k tardaba 0,5-1,9 s)
WINDOW_S = 15.0    # evidencia por origen (baja tasa): flujos DISTINTOS vistos en los
                   # últimos WINDOW_S s de captura. Por tiempo y por flujo, no por chunk:
                   # con snapshots solapados (span > chunk) un flujo sale en varios chunks,
                   # y un chunk descartado por atraso no debe alargar la memoria.
FLOW_ID = ["src_ip", "src_port", "dst_ip", "dst_port", "proto", "start_ts"]


def default_threshold() -> float:
    try:
        d = json.loads((ART / "base_rate.json").read_text())
        for r in d["models"]["xgb"]["detection"]:
            if abs(r["attack_prevalence"] - 0.01) < 1e-9 and r["recall_at_p90"]["thr"] is not None:
                return float(r["recall_at_p90"]["thr"])
    except (OSError, KeyError, ValueError):
        pass
    return 0.99


class LiveDetector:
    def __init__(self, controller: str, thr: float, dry_run: bool, log: Path,
                 chunk_s: float = 5.0):
        self.controller = controller.rstrip("/")
        self.thr = thr
        self.dry_run = dry_run
        self.log = log
        self.det = joblib.load(ART / "xgb.joblib")
        self.attr = joblib.load(ART / "rf.joblib")
        self.scaler = joblib.load(ART / "scaler.joblib")
        self.classes = list(joblib.load(ART / "label_encoder.joblib").classes_)
        self.features: list[str] = joblib.load(ART / "feature_names.joblib")
        self.benign = self.classes.index("BENIGN")
        self.recent: dict[str, float] = {}  # clave de regla → ts última acción
        # src → {flow_id: (t_visto, marcado, etiqueta, (dst, dport))}
        self.src_hist: dict[str, dict[tuple, tuple]] = {}

    # ── inferencia ────────────────────────────────────────────────────
    def score(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Dos umbrales sobre P(ataque) de XGB:
        - estricto (`thr`, precision ≥ 0,9 por FLUJO a prevalencia 1 %): decide los
          destinos bajo ataque distribuido, donde un flujo = un origen (falso).
        - por origen (SRC_THR): la precisión la da la agregación (≥ MIN_FLOWS flujos
          y ≥ MIN_FRAC de los del origen). Con el estricto, slowloris (P mediana
          0,97) quedaba invisible; en vivo ningún benigno supera P 0,5."""
        X = df.reindex(columns=self.features).apply(pd.to_numeric, errors="coerce").fillna(0)
        Xs = self.scaler.transform(X.astype(np.float64))  # DataFrame: el scaler se ajustó con nombres
        p_attack = 1.0 - self.det.predict_proba(Xs)[:, self.benign]
        strict = p_attack >= self.thr
        loose = p_attack >= min(SRC_THR, self.thr)
        labels = np.full(len(df), "BENIGN", dtype=object)
        idx = np.flatnonzero(loose)
        if len(idx):
            sub = idx if len(idx) <= ATTR_MAX else np.random.default_rng(0).choice(
                idx, ATTR_MAX, replace=False)
            pa = self.attr.predict_proba(Xs[sub])
            pa[:, self.benign] = 0.0  # etapa 1 ya decidió "ataque": RF solo elige el tipo
            labels[sub] = np.asarray(self.classes, dtype=object)[pa.argmax(axis=1)]
            if len(sub) < len(idx):
                labels = self._propagate(df, loose, labels, sub)
        return strict, loose, labels

    @staticmethod
    def _propagate(df: pd.DataFrame, loose: np.ndarray, labels: np.ndarray,
                   sub: np.ndarray) -> np.ndarray:
        """Etiqueta los flujos marcados no atribuidos con la mayoritaria de su
        origen; si no, de su destino; si no, la global de la muestra."""
        s = df.iloc[sub]
        lab = pd.Series(labels[sub], index=s.index)
        by_src = lab.groupby(s.src_ip.values).agg(lambda x: x.mode().iat[0])
        by_dst = lab.groupby(s.dst_ip.values).agg(lambda x: x.mode().iat[0])
        glob = lab.mode().iat[0]
        rest = np.setdiff1d(np.flatnonzero(loose), sub)
        r = df.iloc[rest]
        fill = r.src_ip.map(by_src).fillna(r.dst_ip.map(by_dst)).fillna(glob)
        labels[rest] = fill.to_numpy(dtype=object)
        return labels

    # ── agregación en incidentes ──────────────────────────────────────
    def incidents(self, df: pd.DataFrame, strict: np.ndarray, loose: np.ndarray,
                  labels: np.ndarray, now: float) -> list[dict]:
        df = df.assign(_strict=strict, _flag=loose, _label=labels)
        att = df[df._flag]
        out = []  # sin early-return: la ventana por origen debe avanzar en cada chunk
        # destinos bajo ataque distribuido / con origen falsificado
        dist_dsts = set()
        for dst, g in df[df._strict].groupby("dst_ip"):
            if g.src_ip.nunique() >= DIST_SRCS:
                label = Counter(g._label).most_common(1)[0][0]
                proto = int(Counter(g.proto).most_common(1)[0][0])
                match = {"dst_ip": dst, "ip_proto": proto}
                if FAMILY.get(label) == "amplification":
                    # consultas falsificadas rociadas sobre muchas víctimas → se
                    # limita la tasa de consultas al reflector (su servicio sigue vivo)
                    match["tp_dst"] = int(Counter(g.dst_port).most_common(1)[0][0])
                dist_dsts.add(dst)
                out.append({"match": match, "action": "limit", "rate_kbps": LIMIT_KBPS_TIGHT,
                            "label": label, "n_flows": int(len(g)),
                            "n_srcs": int(g.src_ip.nunique()), "reason": "distributed"})
        # evidencia por origen: flujos distintos de los últimos WINDOW_S s. Los ataques
        # de baja tasa (scan, fuerza bruta, slowloris) dejan pocos flujos por chunk y
        # no llegan a MIN_FLOWS en uno solo. Se sigue a los orígenes con algún flujo
        # marcado; de ellos se registran también sus flujos no marcados (para MIN_FRAC).
        track = set(att.src_ip) | set(self.src_hist)
        cols = [c for c in FLOW_ID if c in df.columns]
        for src, g in df[df.src_ip.isin(track)].groupby("src_ip"):
            if g[g._flag].dst_ip.isin(dist_dsts).all() and src not in self.src_hist:
                continue
            h = self.src_hist.setdefault(src, {})
            for fid, fl, lab, dst, dport in zip(g[cols].itertuples(index=False, name=None),
                                                g._flag, g._label, g.dst_ip, g.dst_port):
                prev = h.get(fid)
                h[fid] = (now, fl or (prev is not None and prev[1]),
                          lab if fl else (prev[2] if prev else lab), (dst, dport))
        out += self._source_incidents(now)
        return out

    def _source_incidents(self, now: float) -> list[dict]:
        out = []
        for src, h in list(self.src_hist.items()):
            for fid in [f for f, v in h.items() if v[0] <= now - WINDOW_S]:
                del h[fid]
            marked = [v for v in h.values() if v[1]]
            if not marked:
                del self.src_hist[src]
                continue
            n_att, n_tot = len(marked), len(h)
            if n_att < MIN_FLOWS or n_att / n_tot < MIN_FRAC:
                continue
            label = Counter(v[2] for v in marked).most_common(1)[0][0]
            fam = FAMILY.get(label, "unknown")
            (dst, dport), _ = Counter(v[3] for v in marked).most_common(1)[0]
            if fam == "amplification":
                inc = {"match": {"src_ip": src, "dst_ip": dst, "ip_proto": 17, "tp_dst": dport},
                       "action": "limit", "rate_kbps": LIMIT_KBPS_TIGHT}
            elif src in PROTECTED:
                inc = {"match": {"src_ip": src, "dst_ip": dst}, "action": "limit"}
            elif fam == "recon":
                inc = {"match": {"src_ip": src}, "action": "limit"}
            else:
                inc = {"match": {"src_ip": src}, "action": "drop"}
            inc.update(label=label, n_flows=n_att, frac=round(n_att / n_tot, 3),
                       reason="source")
            out.append(inc)
        return out

    # ── actuación ─────────────────────────────────────────────────────
    def act(self, inc: dict, chunk_end: float) -> None:
        key = json.dumps(inc["match"], sort_keys=True)
        now = time.time()
        if now - self.recent.get(key, 0) < COOLDOWN_S:
            return
        self.recent[key] = now
        body = {**inc["match"], "action": inc["action"], "duration_s": DURATION_S}
        if inc["action"] == "limit":
            body["rate_kbps"] = inc.get("rate_kbps", LIMIT_KBPS)
        ok, resp = True, None
        if not self.dry_run:
            try:
                req = urllib.request.Request(
                    f"{self.controller}/iot/mitigate", data=json.dumps(body).encode(),
                    headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=3) as r:
                    resp = json.loads(r.read())
            except (urllib.error.URLError, ValueError) as e:
                ok, resp = False, str(e)
        done = time.time()
        rec = {"ts": done, "chunk_end": chunk_end, "latency_s": round(done - chunk_end, 3),
               **inc, "ok": ok, "resp": resp, "dry_run": self.dry_run}
        with self.log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"[ACTION] {inc['action']:5} {inc['match']} {inc['label']} "
              f"flows={inc['n_flows']} lat={rec['latency_s']}s ok={ok}", flush=True)

    def process(self, path: Path, chunk_s: float) -> None:
        try:
            df = pd.read_csv(path)
        except (pd.errors.EmptyDataError, OSError):
            return
        if df.empty:
            return
        if len(df) > MAX_ROWS:  # acota la inferencia bajo flood (orígenes/destinos se conservan)
            df = df.sample(MAX_ROWS, random_state=0)
        t0 = time.time()
        strict, flagged, labels = self.score(df)
        chunk_end = float(path.stem.split("_")[1]) + chunk_s
        incs = self.incidents(df, strict, flagged, labels, chunk_end)
        print(f"[CHUNK] {path.name} flows={len(df)} flagged={int(flagged.sum())} "
              f"incidents={len(incs)} infer={time.time() - t0:.2f}s", flush=True)
        with self.log.with_name("chunks.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"chunk": path.name, "flows": int(len(df)),
                                "flagged": int(flagged.sum()), "incidents": len(incs),
                                "infer_s": round(time.time() - t0, 3)}) + "\n")
        for inc in incs:
            self.act(inc, chunk_end)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--live-dir", type=Path, default=ROOT / "data" / "live")
    p.add_argument("--controller", default="http://localhost:8080")
    p.add_argument("--thr", type=float, default=None, help="umbral P(ataque) XGB")
    p.add_argument("--chunk-s", type=float, default=5.0)
    p.add_argument("--dry-run", action="store_true", help="no llama al controlador")
    args = p.parse_args()

    thr = args.thr if args.thr is not None else default_threshold()
    args.live_dir.mkdir(parents=True, exist_ok=True)
    det = LiveDetector(args.controller, thr, args.dry_run, args.live_dir / "actions.jsonl",
                       chunk_s=args.chunk_s)
    print(f"[INIT] det=XGB thr={thr:.6f} src_thr={SRC_THR} attr=RF controller={args.controller} "
          f"chunk={args.chunk_s}s window={WINDOW_S:g}s dry_run={args.dry_run}",
          flush=True)
    seen: set[str] = set()
    while True:
        for f in sorted(args.live_dir.glob("feat_*.csv")):
            if f.name in seen:
                continue
            seen.add(f.name)
            det.process(f, args.chunk_s)
            f.unlink(missing_ok=True)
        time.sleep(0.3)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
