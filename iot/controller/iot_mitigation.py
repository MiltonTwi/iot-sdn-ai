"""
Ryu app: motor de mitigación IoT.

Recibe eventos del detector (HTTP REST) y aplica:
  - DROP   : flow-rule prio 200, idle_timeout configurable
  - LIMIT  : OpenFlow meter (rate-limit) + flow-rule prio 200 con meter action
  - UNBAN  : elimina las reglas instaladas para una IP

Endpoints (puerto 8080 del controller):
  POST /iot/mitigate
    {"src_ip": "10.10.0.99", "action": "drop|limit|unban", "rate_kbps": 1000,
     "duration_s": 60, "dpid": "all",
     # match opcional adicional (al menos uno de src_ip/dst_ip):
     "dst_ip": "10.10.1.10", "ip_proto": 17, "tp_src": 53, "tp_dst": 80}
    Amplificación: la fuente es un reflector legítimo → se bloquea el par
    (reflector, víctima, sport) y no el servidor entero.
  POST /iot/unban
    {"src_ip": "10.10.0.99"}  (o la misma firma de match usada en mitigate)
  GET  /iot/status
    → {"active": [{key, match, action, dpids, remaining_s}, ...]}

Tablas: 0 = seguridad (antispoof 250, mitigación 200); miss → goto 1 (L2).

Convive con dc_switch.py: instala con prio 200 (más alta que la base 1)
para que su decisión preempte al L2 learning.
"""

from __future__ import annotations

import json
import time

from ryu.app.wsgi import ControllerBase, WSGIApplication, route
from ryu.base import app_manager
from ryu.controller import dpset
from ryu.lib import hub
from ryu.ofproto import ofproto_v1_3
from webob import Response


MITIGATION_PRIO = 200
MITIGATION_TABLE = 0
DEFAULT_METER_ID = 1
DEFAULT_DURATION = 60


class IoTMitigation(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {"dpset": dpset.DPSet, "wsgi": WSGIApplication}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dpset: dpset.DPSet = kwargs["dpset"]
        wsgi: WSGIApplication = kwargs["wsgi"]
        wsgi.register(MitigationController, {"app": self})

        # active[key] = {match, action, dpids, meter_id, expires_at}; key = _match_key(match)
        self.active: dict[str, dict] = {}
        self._meter_seq = DEFAULT_METER_ID
        hub.spawn(self._reaper)

    # ─── operaciones públicas (llamadas desde MitigationController) ────

    def mitigate(self, match: dict, action: str, rate_kbps: int = 1000,
                 duration_s: int = DEFAULT_DURATION, dpid_filter: str = "all") -> dict:
        match = _norm_match(match)
        key = _match_key(match)
        installed_dpids: list[int] = []
        if key in self.active:
            self._remove(key)

        meter_id = None
        if action == "limit":
            meter_id = self._next_meter_id()

        for dp in self.dpset.get_all():
            dpid_int, datapath = dp
            if dpid_filter != "all" and str(dpid_int) != dpid_filter:
                continue
            if action == "drop":
                self._install_drop(datapath, match, key, duration_s)
            elif action == "limit":
                self._install_meter(datapath, meter_id, rate_kbps)
                self._install_limit(datapath, match, key, meter_id, duration_s)
            else:
                raise ValueError(f"action desconocida: {action}")
            installed_dpids.append(dpid_int)

        self.active[key] = {
            "match": match,
            "action": action,
            "rate_kbps": rate_kbps if action == "limit" else None,
            "meter_id": meter_id,
            "dpids": installed_dpids,
            "started_at": time.time(),
            "expires_at": time.time() + duration_s,
        }
        self.logger.info("MITIGATE %s action=%s dpids=%s", key, action, installed_dpids)
        return {"key": key, "src_ip": match.get("src_ip"), "action": action,
                "dpids": installed_dpids}

    def unban(self, match: dict) -> dict:
        key = _match_key(_norm_match(match))
        if key not in self.active:
            return {"key": key, "status": "not_active"}
        self._remove(key)
        return {"key": key, "status": "removed"}

    def status(self) -> dict:
        now = time.time()
        return {
            "active": [
                {"key": key, "src_ip": info["match"].get("src_ip"), **info,
                 "remaining_s": max(0, info["expires_at"] - now)}
                for key, info in self.active.items()
            ]
        }

    # ─── helpers OF ────────────────────────────────────────────────────

    def _install_drop(self, datapath, m: dict, key: str, duration_s: int) -> None:
        ofp = datapath.ofproto
        parser = datapath.ofproto_parser
        match = _of_match(parser, m)
        inst = []  # sin instructions = drop implícito en algunas versiones; explícito:
        # Usamos lista de instructions vacía: en OF1.3 = drop.
        mod = parser.OFPFlowMod(
            datapath=datapath, table_id=MITIGATION_TABLE, priority=MITIGATION_PRIO,
            match=match, instructions=inst,
            idle_timeout=duration_s, hard_timeout=duration_s,
            command=ofp.OFPFC_ADD, flags=ofp.OFPFF_SEND_FLOW_REM,
            cookie=self._cookie_for(key),
        )
        datapath.send_msg(mod)

    def _install_meter(self, datapath, meter_id: int, rate_kbps: int) -> None:
        ofp = datapath.ofproto
        parser = datapath.ofproto_parser
        band = parser.OFPMeterBandDrop(rate=rate_kbps, burst_size=rate_kbps // 4)
        mod = parser.OFPMeterMod(
            datapath=datapath, command=ofp.OFPMC_ADD,
            flags=ofp.OFPMF_KBPS, meter_id=meter_id, bands=[band],
        )
        datapath.send_msg(mod)

    def _install_limit(self, datapath, m: dict, key: str, meter_id: int, duration_s: int) -> None:
        ofp = datapath.ofproto
        parser = datapath.ofproto_parser
        match = _of_match(parser, m)
        inst = [
            parser.OFPInstructionMeter(meter_id=meter_id, type_=ofp.OFPIT_METER),
            parser.OFPInstructionGotoTable(table_id=MITIGATION_TABLE + 1),
        ]
        mod = parser.OFPFlowMod(
            datapath=datapath, table_id=MITIGATION_TABLE, priority=MITIGATION_PRIO,
            match=match, instructions=inst,
            idle_timeout=duration_s, hard_timeout=duration_s,
            command=ofp.OFPFC_ADD, cookie=self._cookie_for(key),
        )
        datapath.send_msg(mod)

    def _remove(self, key: str) -> None:
        info = self.active.pop(key, None)
        if not info:
            return
        cookie = self._cookie_for(key)
        for dpid_int in info["dpids"]:
            dp = self.dpset.get(dpid_int)
            if not dp:
                continue
            ofp = dp.ofproto
            parser = dp.ofproto_parser
            mod = parser.OFPFlowMod(
                datapath=dp, command=ofp.OFPFC_DELETE,
                table_id=MITIGATION_TABLE, cookie=cookie, cookie_mask=0xFFFFFFFFFFFFFFFF,
                out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY,
            )
            dp.send_msg(mod)
            if info.get("meter_id"):
                meter_mod = parser.OFPMeterMod(
                    datapath=dp, command=ofp.OFPMC_DELETE,
                    flags=ofp.OFPMF_KBPS, meter_id=info["meter_id"], bands=[],
                )
                dp.send_msg(meter_mod)
        self.logger.info("UNBAN %s", key)

    def _next_meter_id(self) -> int:
        self._meter_seq += 1
        return self._meter_seq

    @staticmethod
    def _cookie_for(key: str) -> int:
        h = 0
        for c in key:
            h = (h * 131 + ord(c)) & 0xFFFFFFFFFFFFFFFF
        return h | 0x1000000000000000  # bit alto = mitigation

    def _reaper(self) -> None:
        """Limpia entradas expiradas de self.active (la regla muere por hard_timeout)."""
        while True:
            now = time.time()
            stale = [ip for ip, info in self.active.items() if info["expires_at"] <= now]
            for ip in stale:
                self.active.pop(ip, None)
            hub.sleep(5)


MATCH_FIELDS = ("src_ip", "dst_ip", "ip_proto", "tp_src", "tp_dst")


def _norm_match(body: dict) -> dict:
    m = {k: body[k] for k in MATCH_FIELDS if body.get(k) not in (None, "")}
    for k in ("ip_proto", "tp_src", "tp_dst"):
        if k in m:
            m[k] = int(m[k])
    if "src_ip" not in m and "dst_ip" not in m:
        raise ValueError("match requiere src_ip o dst_ip")
    if ("tp_src" in m or "tp_dst" in m) and m.get("ip_proto") not in (6, 17):
        raise ValueError("tp_src/tp_dst requieren ip_proto 6 (tcp) o 17 (udp)")
    return m


def _match_key(m: dict) -> str:
    """Clave estable de una regla. Solo-src → la IP (compatible con la API previa)."""
    if set(m) == {"src_ip"}:
        return m["src_ip"]
    return "|".join(f"{k}={m[k]}" for k in MATCH_FIELDS if k in m)


def _of_match(parser, m: dict):
    f = {"eth_type": 0x0800}
    if "src_ip" in m:
        f["ipv4_src"] = m["src_ip"]
    if "dst_ip" in m:
        f["ipv4_dst"] = m["dst_ip"]
    if "ip_proto" in m:
        f["ip_proto"] = m["ip_proto"]
    l4 = {6: "tcp", 17: "udp"}.get(m.get("ip_proto"))
    if l4 and "tp_src" in m:
        f[f"{l4}_src"] = m["tp_src"]
    if l4 and "tp_dst" in m:
        f[f"{l4}_dst"] = m["tp_dst"]
    return parser.OFPMatch(**f)


class MitigationController(ControllerBase):
    def __init__(self, req, link, data, **config):
        super().__init__(req, link, data, **config)
        self.app: IoTMitigation = data["app"]

    @route("iot", "/iot/mitigate", methods=["POST"])
    def mitigate(self, req, **_):
        try:
            body = json.loads(req.body or b"{}")
            action = body.get("action", "drop")
            if action == "unban":
                res = self.app.unban(body)
            else:
                rate = int(body.get("rate_kbps", 1000))
                dur = int(body.get("duration_s", DEFAULT_DURATION))
                dpid = body.get("dpid", "all")
                res = self.app.mitigate(body, action, rate, dur, dpid)
            return Response(content_type="application/json", body=json.dumps(res).encode())
        except Exception as e:
            return Response(status=400, body=str(e).encode())

    @route("iot", "/iot/unban", methods=["POST"])
    def unban(self, req, **_):
        try:
            body = json.loads(req.body or b"{}")
            res = self.app.unban(body)
            return Response(content_type="application/json", body=json.dumps(res).encode())
        except Exception as e:
            return Response(status=400, body=str(e).encode())

    @route("iot", "/iot/status", methods=["GET"])
    def status(self, req, **_):
        return Response(content_type="application/json", body=json.dumps(self.app.status()).encode())
