#!/bin/bash
# Qué recibe la víctima durante DNS amplification, sin y con LIMIT. Corre en el contenedor mininet.
set -u
pidof(){ pgrep -f "is mininet:$1$" | head -1; }
ATK=$(pidof attacker); VIC=$(pidof camfront); C=http://controller:8080
cnt(){ mnexec -a "$VIC" timeout 3 tcpdump -i any -n -l 2>/dev/null | awk '/ARP/{a++} /\.53 >/{d++} END{printf "dns_resp=%d/s arp=%d/s total=%d/s", d/3, a/3, NR/3}'; }
mnexec -a "$ATK" timeout 40 python3 /root/iot/attacks/runner.py --scenario dns_amplification --duration 30 --episode 1 >/dev/null 2>&1 &
sleep 6; echo "SIN regla: $(cnt)"
curl -s -X POST $C/iot/mitigate -H 'Content-Type: application/json' \
  -d '{"dst_ip":"10.10.0.13","ip_proto":17,"tp_dst":53,"action":"limit","rate_kbps":64,"duration_s":30}' >/dev/null
sleep 3; echo "CON limit: $(cnt)"
curl -s -X POST $C/iot/unban -H 'Content-Type: application/json' -d '{"dst_ip":"10.10.0.13","ip_proto":17,"tp_dst":53}' >/dev/null
wait
