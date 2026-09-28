#!/bin/bash
# ¿El LIMIT (meter) sobre consultas al reflector frena la amplificación? Corre en el contenedor mininet.
set -u
pidof(){ pgrep -f "is mininet:$1$" | head -1; }
ATK=$(pidof attacker); REF=$(pidof dnsserver); VIC=$(pidof camfront)
C=http://controller:8080
rx(){ mnexec -a "$1" awk 'NR>2 && $1!="lo:"{sub(/.*:/,"");print $2;exit}' /proc/net/dev; }
pps(){ local a b; a=$(rx "$1"); sleep 3; b=$(rx "$1"); echo $(( (b - a) / 3 )); }
mnexec -a "$ATK" timeout 40 python3 /root/iot/attacks/runner.py --scenario dns_amplification --duration 35 --episode 1 >/dev/null 2>&1 &
sleep 6
echo "SIN regla : reflector rx=$(pps $REF) pps  victima rx=$(pps $VIC) pps"
curl -s -X POST $C/iot/mitigate -H 'Content-Type: application/json' \
  -d '{"dst_ip":"10.10.0.13","ip_proto":17,"tp_dst":53,"action":"limit","rate_kbps":64,"duration_s":30}'; echo
sleep 3
echo "CON limit : reflector rx=$(pps $REF) pps  victima rx=$(pps $VIC) pps"
ovs-ofctl -O OpenFlow13 dump-flows s_iot_0 | grep "priority=200" | sed 's/cookie=[^,]*, //'
ovs-ofctl -O OpenFlow13 meter-stats s_iot_0 | head -8
ovs-ofctl -O OpenFlow13 dump-meters s_iot_0 | head -4
curl -s -X POST $C/iot/unban -H 'Content-Type: application/json' -d '{"dst_ip":"10.10.0.13","ip_proto":17,"tp_dst":53}'; echo
wait
