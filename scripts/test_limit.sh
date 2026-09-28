#!/bin/bash
# Verifica que action=limit deja pasar tráfico bajo la tasa (no debe comportarse como drop).
# Corre DENTRO del contenedor mininet.
set -u
pidof(){ pgrep -f "is mininet:$1$" | head -1; }
ATK=$(pidof attacker); ATK_IP=10.10.0.99; VIC_IP=10.10.0.12
C=http://controller:8080
api(){ curl -s -X POST "$C/iot/$1" -H 'Content-Type: application/json' -d "$2"; echo; }
api unban "{\"src_ip\":\"$ATK_IP\"}" >/dev/null
echo ">>> sin regla:";  mnexec -a "$ATK" ping -c 5 -i 0.2 -W 1 $VIC_IP | grep -E "packets"
api mitigate "{\"src_ip\":\"$ATK_IP\",\"action\":\"limit\",\"rate_kbps\":10000,\"duration_s\":30}"
sleep 2
echo ">>> con LIMIT 10 Mbps:"; mnexec -a "$ATK" ping -c 5 -i 0.2 -W 1 $VIC_IP | grep -E "packets"
for b in s_iot_0; do ovs-ofctl -O OpenFlow13 dump-flows $b | grep -E "priority=200|table=1" ; done
api unban "{\"src_ip\":\"$ATK_IP\"}"

echo ">>> match compuesto (amplificación): drop solo reflector->víctima udp sport 53"
api mitigate '{"src_ip":"10.10.0.13","dst_ip":"10.10.1.10","ip_proto":17,"tp_src":53,"action":"drop","duration_s":20}'
ovs-ofctl -O OpenFlow13 dump-flows s_iot_0 | grep "priority=200"
api mitigate '{"src_ip":"10.10.0.13","dst_ip":"10.10.1.10","ip_proto":17,"tp_src":53,"action":"unban"}'
echo ">>> tablas s_iot_0 (prio0):"; ovs-ofctl -O OpenFlow13 dump-flows s_iot_0 | grep "priority=0"
