#!/bin/bash
# Diagnóstico de amplificación DNS: ¿spoofing sale? ¿reflector responde? ¿víctima recibe?
set -u
pidof_host(){ pgrep -f "is mininet:$1" | head -1; }
ATK=$(pidof_host attacker); DNS=$(pidof_host dnsserver); VIC=$(pidof_host camfront)
echo "PIDs  attacker=$ATK  dnsserver(reflector)=$DNS  camfront(victima)=$VIC"
[ -z "$ATK" ] && { echo "sin attacker"; exit 1; }
RD=/tmp/ampl_diag; mkdir -p $RD; rm -f $RD/*.pcap

mnexec -a $DNS tcpdump -i any -n -s0 -w $RD/reflector.pcap udp >/dev/null 2>&1 &
TD1=$!
mnexec -a $VIC tcpdump -i any -n -s0 -w $RD/victim.pcap udp >/dev/null 2>&1 &
TD2=$!
sleep 1
echo ">>> lanzando dns_amplification (duration 10)..."
mnexec -a $ATK python3 /root/iot/attacks/runner.py --scenario dns_amplification --duration 10 2>&1 | tail -6
sleep 2
kill $TD1 $TD2 2>/dev/null; sleep 1

echo
echo "===== REFLECTOR: queries entrantes (udp dst port 53) ====="
Q=$(mnexec -a $DNS tcpdump -nr $RD/reflector.pcap 'udp dst port 53' 2>/dev/null)
echo "  total queries: $(echo \"$Q\" | grep -c 'IP ')"
echo "  source IPs distintos (spoofing check):"
echo "$Q" | awk '{print $3}' | sed -E 's/\.[0-9]+$//' | sort -u | head -12
echo "  (conteo distintos: $(echo "$Q" | awk '{print $3}' | sed -E 's/\.[0-9]+$//' | sort -u | grep -c .))"
echo "  muestra:"; echo "$Q" | head -3

echo
echo "===== REFLECTOR: respuestas salientes (udp src port 53) ====="
R=$(mnexec -a $DNS tcpdump -nr $RD/reflector.pcap 'udp src port 53' 2>/dev/null)
echo "  total respuestas: $(echo "$R" | grep -c 'IP ')"
echo "  muestra (con length):"; echo "$R" | head -3

echo
echo "===== VICTIMA (camfront): respuestas recibidas del reflector ====="
V=$(mnexec -a $VIC tcpdump -nr $RD/victim.pcap 'udp src port 53' 2>/dev/null)
echo "  total recibidas: $(echo "$V" | grep -c 'IP ')"
echo "  muestra:"; echo "$V" | head -3
