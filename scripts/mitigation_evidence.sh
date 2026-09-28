#!/bin/bash
# Evidencia cuantitativa de mitigación (pega #5) + anti-spoof ARP (pega #4).
# Corre DENTRO del contenedor mininet. Escribe JSON a ml_extra/artifacts/.
# Mide paquetes que llegan a la víctima ANTES y DESPUÉS de instalar el DROP.
set -u
ART=/root/data/../ml_extra/artifacts
mkdir -p "$ART" 2>/dev/null || ART=/root
pidof(){ pgrep -f "is mininet:$1$" | head -1; }
ATK=$(pidof attacker); VIC=$(pidof httpserve)
ATK_IP=10.10.0.99; VIC_IP=10.10.0.12; PORT=9999
echo "attacker=$ATK ($ATK_IP)  victima=$VIC ($VIC_IP)"
[ -z "$ATK" ] || [ -z "$VIC" ] && { echo "faltan hosts"; exit 1; }

# limpia mitigaciones previas
curl -s -X POST http://controller:8080/iot/mitigate -H 'Content-Type: application/json' \
  -d "{\"src_ip\":\"$ATK_IP\",\"action\":\"unban\"}" >/dev/null 2>&1 || true
sleep 2

count_at_victim(){  # cuenta paquetes UDP:$PORT en la víctima durante $1 s bajo flood
  mnexec -a "$VIC" timeout "$1" tcpdump -i any -n "udp port $PORT" 2>/dev/null | grep -c "IP "
}

flood(){  # attacker floodea UDP a la víctima durante $1 s
  mnexec -a "$ATK" timeout "$1" python3 -c "
import socket,time,sys
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
end=time.time()+float(sys.argv[1]); p=b'x'*200
while time.time()<end:
    try: s.sendto(p,('$VIC_IP',$PORT))
    except OSError: pass
" "$1" >/dev/null 2>&1 &
}

echo ">>> BASELINE (sin mitigación): flood 5s, cuento en víctima"
flood 6; sleep 1
BASE=$(count_at_victim 4)
wait 2>/dev/null; sleep 1
echo "  paquetes recibidos (baseline): $BASE"

echo ">>> instalando DROP sobre $ATK_IP"
RESP=$(curl -s -X POST http://controller:8080/iot/mitigate -H 'Content-Type: application/json' \
  -d "{\"src_ip\":\"$ATK_IP\",\"action\":\"drop\",\"duration_s\":60}")
echo "  respuesta: $RESP"
sleep 2

echo ">>> POST-MITIGACIÓN: flood 5s, cuento en víctima"
flood 6; sleep 1
MIT=$(count_at_victim 4)
wait 2>/dev/null; sleep 1
echo "  paquetes recibidos (mitigado): $MIT"

# reglas DROP instaladas
DROPS=$(for b in $(ovs-vsctl list-br); do ovs-ofctl -O OpenFlow13 dump-flows "$b" 2>/dev/null | grep -c "priority=200.*drop"; done | paste -sd+ | sed 's/+/ /g')
DROPN=0; for x in $DROPS; do DROPN=$((DROPN+x)); done

RED=0
[ "$BASE" -gt 0 ] && RED=$(python3 -c "print(round(100*(1-$MIT/$BASE),1))")
echo ">>> reducción throughput víctima: ${RED}%  (drop rules=$DROPN)"

# limpia
curl -s -X POST http://controller:8080/iot/mitigate -H 'Content-Type: application/json' \
  -d "{\"src_ip\":\"$ATK_IP\",\"action\":\"unban\"}" >/dev/null 2>&1 || true

python3 - "$BASE" "$MIT" "$RED" "$DROPN" > "$ART/mitigation_evidence.json" <<'PY'
import json,sys
b,m,red,dn=int(sys.argv[1]),int(sys.argv[2]),float(sys.argv[3]),int(sys.argv[4])
json.dump({"victim_pkts_baseline":b,"victim_pkts_mitigated":m,
           "throughput_reduction_pct":red,"drop_rules_installed":dn,
           "method":"UDP flood attacker->victim; tcpdump count at victim before/after DROP"},
          sys.stdout,indent=2)
PY
echo; echo "JSON -> $ART/mitigation_evidence.json"
