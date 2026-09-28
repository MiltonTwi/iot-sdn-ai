"""
L2 learning switch — sustituye a dc_switch.py del SdnShare base.

Aprende src_mac → in_port por dpid. Instala flow-mod priority=1 al ver el
destino. Convive con iot_mitigation (prio 200) y iot_antispoof (prio 250).

Necesario porque dc_switch.py / learning_switch.py del base requieren
configuración estática que no encaja con nuestra topología auto-generada.
"""

from __future__ import annotations

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.lib.packet import ethernet, packet
from ryu.ofproto import ofproto_v1_3

L2_TABLE = 1  # tabla 0 reservada a antispoof/mitigación (iot_mitigation hace goto 1)


class IoTL2Switch(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # mac_to_port[dpid][mac] = port
        self.mac_to_port: dict[int, dict[str, int]] = {}
        self._pktin_n = 0  # DEBUG

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def _switch_features(self, ev):
        dp = ev.msg.datapath
        ofp = dp.ofproto
        parser = dp.ofproto_parser

        # Tabla 0 = seguridad (antispoof prio 250, mitigación prio 200); su miss
        # sigue a la tabla 1 = reenvío L2. Así un LIMIT (meter + goto 1) reenvía
        # de verdad en vez de caer en una tabla vacía (= drop).
        match = parser.OFPMatch()
        dp.send_msg(parser.OFPFlowMod(
            datapath=dp, table_id=0, priority=0, match=match,
            instructions=[parser.OFPInstructionGotoTable(L2_TABLE)],
        ))
        # table-miss de L2 → CONTROLLER
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=dp, table_id=L2_TABLE, priority=0, match=match, instructions=inst,
        )
        dp.send_msg(mod)
        self.logger.info("L2 switch: table-miss instalada en dpid=%s", dp.id)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in(self, ev):
        msg = ev.msg
        dp = msg.datapath
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None:
            return
        # ignora LLDP (control de topología)
        if eth.ethertype == 0x88cc:
            return

        dpid = dp.id
        self.mac_to_port.setdefault(dpid, {})

        # aprende src
        self.mac_to_port[dpid][eth.src] = in_port

        # decide salida
        out_port = self.mac_to_port[dpid].get(eth.dst, ofp.OFPP_FLOOD)
        self._pktin_n += 1  # DEBUG
        if self._pktin_n <= 25:
            self.logger.info("PKTIN #%d dpid=%s in=%s type=0x%04x %s->%s out=%s",
                             self._pktin_n, dpid, in_port, eth.ethertype, eth.src, eth.dst,
                             "FLOOD" if out_port == ofp.OFPP_FLOOD else out_port)
        actions = [parser.OFPActionOutput(out_port)]

        # si conocemos destino: flow-mod prio 1, evita futuros packet-in
        if out_port != ofp.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=eth.dst, eth_src=eth.src)
            inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
            mod = parser.OFPFlowMod(
                datapath=dp, table_id=L2_TABLE, priority=1, match=match, instructions=inst,
                idle_timeout=60, hard_timeout=300,
            )
            dp.send_msg(mod)

        # despacha el paquete actual
        data = msg.data if msg.buffer_id == ofp.OFP_NO_BUFFER else None
        out = parser.OFPPacketOut(
            datapath=dp, buffer_id=msg.buffer_id, in_port=in_port,
            actions=actions, data=data,
        )
        dp.send_msg(out)
