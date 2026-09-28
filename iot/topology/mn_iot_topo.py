#!/usr/bin/env python3
"""
Mininet IoT topology.

Lee network_config.iot.yaml (auto-generado), construye la red, arranca el
controlador SDN remoto (Ryu via container `controller`) y deja a Mininet con
la consola interactiva.

Adicionalmente al base spine-leaf:
  - exporta tabla de hosts a /tmp/iot_hosts.json (consumida por dashboard)
  - escribe metadata por host en /etc/hosts dentro del container Mininet
  - lanza simuladores de dispositivos vía iot/devices/runner.py si --auto-traffic
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController


def _wait_rstp(switches, timeout: int = 60, stable_s: int = 6) -> None:
    """Espera convergencia RSTP: ningún puerto en Learning y nº de puertos
    Forwarding estable durante `stable_s` segundos."""
    import time as _t

    sw0 = switches[0]
    t0 = _t.time()
    last, since = -1, _t.time()
    while _t.time() - t0 < timeout:
        out = sw0.cmd("ovs-vsctl --format=csv --no-headings --columns=rstp_status list port")
        fwd = out.count("Forwarding")
        lrn = out.count("Learning")
        if fwd != last:
            last, since = fwd, _t.time()
        elif lrn == 0 and fwd > 0 and _t.time() - since >= stable_s:
            info(f"*** RSTP convergido: {fwd} puertos Forwarding ({_t.time() - t0:.0f}s)\n")
            return
        _t.sleep(1)
    info(f"*** RSTP: timeout {timeout}s (Forwarding={last}), sigo igual\n")


def build(config_path: str, ctrl: str = "127.0.0.1", auto_traffic: bool = False, no_cli: bool = False) -> None:
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    net = Mininet(controller=RemoteController, link=TCLink, switch=OVSSwitch)
    info("*** Adding controller\n")
    c0 = net.addController("ctrl", controller=RemoteController, ip=ctrl, port=6633)

    info("*** Adding switches\n")
    switches: dict[str, object] = {}
    # dpid único por bridge para evitar colisión DPSet en Ryu (spines y leafs
    # colisionaban con sequential dpids → flow-mods solo a 8/10 switches).
    # Convenio: spines = 0x10X, iot leafs = 0x20X.
    for idx, sw in enumerate(cfg["switches"]):
        name = sw["name"]
        if name.startswith("s_spine_"):
            n = int(name.rsplit("_", 1)[-1])
            dpid = f"{0x100 + n:016x}"
        elif name.startswith("s_iot_"):
            n = int(name.rsplit("_", 1)[-1])
            dpid = f"{0x200 + n:016x}"
        else:
            dpid = f"{idx + 1:016x}"
        switches[name] = net.addSwitch(name, dpid=dpid)

    info("*** Adding inter-switch links\n")
    for link in cfg["links"]:
        net.addLink(
            switches[link["source"]],
            switches[link["target"]],
            port1=link["source_port"],
            port2=link["target_port"],
        )

    info("*** Adding hosts\n")
    hosts: dict[str, object] = {}
    for h in cfg["hosts"]:
        host = net.addHost(
            h["name"],
            ip=h["ip"],
            mac=h["mac"],
            defaultRoute=h["default_route"],
        )
        hosts[h["name"]] = host
        net.addLink(host, switches[h["connected_to"]], port1=h["port"])

    info("*** Starting network\n")
    net.build()
    c0.start()
    for sw in switches.values():
        sw.start([c0])

    # Spine-leaf con 2 spines = malla con loops L2. El L2 switch hace FLOOD →
    # broadcast storm + MAC flapping (flows hairpin in_port==out_port) y
    # anti-spoof ve el mismo host por uplinks distintos. RSTP bloquea los
    # enlaces redundantes; OVS respeta el estado RSTP también en OFPP_FLOOD.
    info("*** RSTP en todos los bridges (anti-loop)\n")
    for sw in switches.values():
        sw.cmd(f"ovs-vsctl set bridge {sw.name} rstp_enable=true")
    _wait_rstp(list(switches.values()))

    info("*** staticArp — popula tablas ARP all-to-all\n")
    try:
        net.staticArp()
        info("*** staticArp OK\n")
    except Exception as e:
        info(f"*** staticArp falló: {e}\n")

    hosts_meta = [
        {k: v for k, v in h.items() if k != "default_route"} for h in cfg["hosts"]
    ]
    Path("/tmp/iot_hosts.json").write_text(json.dumps(hosts_meta, indent=2))
    info(f"*** /tmp/iot_hosts.json escrito con {len(hosts_meta)} hosts\n")

    if auto_traffic:
        info("*** Lanzando simuladores en cada host (auto-traffic)\n")
        for h in cfg["hosts"]:
            if h.get("role") in (
                "mqtt-broker",
                "coap-server",
                "http-server",
                "dns-server",
                "ntp-server",
                "ssdp-server",
            ):
                _start_server(hosts[h["name"]], h)
            elif h.get("role") == "attacker":
                continue
            else:
                _start_device(hosts[h["name"]], h)

    if no_cli:
        info("*** Modo --no-cli: red levantada, durmiendo (Ctrl+C para detener)\n")
        try:
            import time as _t
            while True:
                _t.sleep(60)
        except KeyboardInterrupt:
            pass
    else:
        CLI(net)
    info("*** Stopping network\n")
    net.stop()


def _start_server(host, meta) -> None:
    role = meta["role"]
    cmd = {
        "mqtt-broker": "python3 /root/iot/devices/servers/mqtt_broker.py &",
        "coap-server": "python3 /root/iot/devices/servers/coap_server.py &",
        "http-server": "python3 /root/iot/devices/servers/http_server.py 80 &",
        "dns-server":  "python3 /root/iot/devices/servers/dns_server.py &",
        "ntp-server":  "python3 /root/iot/devices/servers/ntp_server.py &",
        "ssdp-server": "python3 /root/iot/devices/servers/ssdp_server.py &",
    }.get(role)
    if cmd:
        host.cmd(cmd)


def _start_device(host, meta) -> None:
    args = (
        f"--name {meta['name']} "
        f"--proto {meta['proto']} "
        f"--dst-name {meta['dst']} "
        f"--rate {meta['rate_pps']} "
        f"--payload {meta['payload']} "
        f"--zone {meta.get('zone', 'unknown')}"
    )
    host.cmd(f"python3 /root/iot/devices/runner.py {args} >/tmp/{meta['name']}.log 2>&1 &")


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Uso: sudo ./mn_iot_topo.py <network_config.iot.yaml> [controller_ip] [--auto-traffic]"
        )
        sys.exit(1)
    config_path = sys.argv[1]
    ctrl = os.getenv("SDN_CONTROLLER", "127.0.0.1")
    if len(sys.argv) > 2 and not sys.argv[2].startswith("--"):
        ctrl = sys.argv[2]
    auto_traffic = "--auto-traffic" in sys.argv
    no_cli = "--no-cli" in sys.argv
    setLogLevel("info")
    build(config_path, ctrl, auto_traffic, no_cli)


if __name__ == "__main__":
    main()
