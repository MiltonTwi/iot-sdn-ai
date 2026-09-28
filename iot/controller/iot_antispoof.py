"""
Ryu app: Anti-Spoofing IP-MAC binding.

Aprende (dpid, in_port, ipv4_src, eth_src) la primera vez que ve un host en
un puerto de BORDE (leaf, no enlace switch-switch descubierto por LLDP).
A partir de ahí, si una IP aparece con MAC distinta o desde otro puerto de
borde, instala DROP flow-rule sobre esa combinación inválida + emite alerta.

Convive con dc_switch.py:
  - escucha EventOFPPacketIn (no consume el paquete, solo observa)
  - instala flow-rules de bloqueo con priority 250 (> mitigation 200)

Endpoint:
  GET  /iot/antispoof/bindings  → {"bindings": [{dpid, ip, mac, port}, ...]}
  GET  /iot/antispoof/violations → {"violations": [{ts, dpid, ip, mac, port}, ...]}
"""

from __future__ import annotations

import json
import time

from ryu.app.wsgi import ControllerBase, WSGIApplication, route
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, set_ev_cls
from ryu.lib.packet import ethernet, packet, arp, ipv4
from ryu.ofproto import ofproto_v1_3
from ryu.topology import event as topo_event
from webob import Response

# EventLinkAdd requiere el app de descubrimiento LLDP (con --observe-links)
app_manager.require_app("ryu.topology.switches", api_style=True)


ANTISPOOF_PRIO = 250
ANTISPOOF_COOKIE = 0x2000000000000000
SPINE_DPID_MAX = 0x1FF  # convenio mn_iot_topo: spines 0x10X, leafs 0x20X


class IoTAntiSpoof(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {"wsgi": WSGIApplication}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        wsgi: WSGIApplication = kwargs["wsgi"]
        wsgi.register(AntiSpoofController, {"app": self})

        # bindings[(dpid, ip)] = {mac, port, ts}
        self.bindings: dict[tuple[int, str], dict] = {}
        self.violations: list[dict] = []
        self.max_violations = 200
        # (dpid, port) switch-switch. El binding IP→(MAC,puerto) solo tiene
        # sentido en puertos de borde: por un uplink llegan muchos hosts y, con
        # caminos redundantes, el mismo host por uplinks distintos (falso SPOOF).
        self.trunk_ports: set[tuple[int, int]] = set()
        self.dps: dict[int, object] = {}

    @set_ev_cls(topo_event.EventLinkAdd)
    def _link_add(self, ev):
        for end in (ev.link.src, ev.link.dst):
            key = (end.dpid, end.port_no)
            if key in self.trunk_ports:
                continue
            self.trunk_ports.add(key)
            # purga lo aprendido/bloqueado en ese puerto antes del descubrimiento
            self.bindings = {
                k: b for k, b in self.bindings.items()
                if not (k[0] == end.dpid and b["port"] == end.port_no)
            }
            dp = self.dps.get(end.dpid)
            if dp is not None:
                self._unblock_port(dp, end.port_no)

    def _is_edge(self, dpid: int, port: int) -> bool:
        return dpid > SPINE_DPID_MAX and (dpid, port) not in self.trunk_ports

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in(self, ev):
        msg = ev.msg
        dp = msg.datapath
        in_port = msg.match["in_port"]
        self.dps[dp.id] = dp
        if not self._is_edge(dp.id, in_port):
            return
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None:
            return

        ip_layer = pkt.get_protocol(ipv4.ipv4)
        arp_layer = pkt.get_protocol(arp.arp)
        if ip_layer is not None:
            ip_src = ip_layer.src
        elif arp_layer is not None:
            ip_src = arp_layer.src_ip
        else:
            return

        mac_src = eth.src
        key = (dp.id, ip_src)
        bind = self.bindings.get(key)

        if bind is None:
            self.bindings[key] = {"mac": mac_src, "port": in_port, "ts": time.time()}
            self.logger.debug("LEARN dpid=%s ip=%s mac=%s port=%s", dp.id, ip_src, mac_src, in_port)
            return

        if bind["mac"] != mac_src or bind["port"] != in_port:
            self._record_violation(dp.id, ip_src, mac_src, in_port, bind)
            self._block(dp, ip_src, mac_src, in_port)

    def _record_violation(self, dpid, ip, mac, port, bind):
        v = {
            "ts": time.time(), "dpid": dpid, "ip": ip,
            "observed_mac": mac, "expected_mac": bind["mac"],
            "observed_port": port, "expected_port": bind["port"],
        }
        self.violations.append(v)
        if len(self.violations) > self.max_violations:
            self.violations = self.violations[-self.max_violations:]
        self.logger.warning("SPOOF dpid=%s ip=%s mac=%s (esperado %s)", dpid, ip, mac, bind["mac"])

    def _block(self, dp, ip, mac, port):
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        match = parser.OFPMatch(in_port=port, eth_type=0x0800, ipv4_src=ip, eth_src=mac)
        mod = parser.OFPFlowMod(
            datapath=dp, table_id=0, priority=ANTISPOOF_PRIO,
            match=match, instructions=[],  # drop
            idle_timeout=300, hard_timeout=300,
            command=ofp.OFPFC_ADD,
            cookie=ANTISPOOF_COOKIE,
        )
        dp.send_msg(mod)

    def _unblock_port(self, dp, port):
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        mod = parser.OFPFlowMod(
            datapath=dp, table_id=ofp.OFPTT_ALL, command=ofp.OFPFC_DELETE,
            out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY,
            cookie=ANTISPOOF_COOKIE, cookie_mask=0xFFFFFFFFFFFFFFFF,
            match=parser.OFPMatch(in_port=port),
        )
        dp.send_msg(mod)


class AntiSpoofController(ControllerBase):
    def __init__(self, req, link, data, **config):
        super().__init__(req, link, data, **config)
        self.app: IoTAntiSpoof = data["app"]

    @route("iot", "/iot/antispoof/bindings", methods=["GET"])
    def bindings(self, req, **_):
        out = [
            {"dpid": dpid, "ip": ip, **info}
            for (dpid, ip), info in self.app.bindings.items()
        ]
        return Response(content_type="application/json", body=json.dumps({"bindings": out}).encode())

    @route("iot", "/iot/antispoof/violations", methods=["GET"])
    def violations(self, req, **_):
        return Response(content_type="application/json",
                        body=json.dumps({"violations": self.app.violations[-100:]}).encode())
