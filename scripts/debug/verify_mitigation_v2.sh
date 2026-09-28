#!/bin/bash
# Verify mitigation chain — restart topology cleanly first.

echo "=== STEP 1: mininet cleanup ==="
docker exec sdnshare-mininet-1 mn -c 2>&1 | tail -2

echo "=== STEP 2: launch topology (no auto-traffic, no-cli) ==="
docker exec -d sdnshare-mininet-1 bash -c \
  "python3 /root/iot/topology/mn_iot_topo.py /root/iot/topology/network_config.iot.yaml --no-cli > /tmp/topo3.log 2>&1"

echo "=== STEP 3: wait 45s for stabilization ==="
sleep 45

echo "=== STEP 4: locate attacker ==="
ATK_PID=$(docker exec sdnshare-mininet-1 pgrep -f "bash --norc --noediting -is mininet:attacker" | head -1)
echo "ATK_PID=$ATK_PID"
docker exec sdnshare-mininet-1 ls /proc/$ATK_PID/ns/ 2>&1 | head -2

echo "=== STEP 5: ping test ==="
docker exec sdnshare-mininet-1 mnexec -a $ATK_PID ping -c3 -W3 10.10.0.12 2>&1 | tail -5

echo "=== STEP 6: pre-mitigation flows ==="
docker exec sdnshare-mininet-1 ovs-ofctl dump-flows s_spine_1 -O OpenFlow13 2>&1 | head -3
docker exec sdnshare-mininet-1 ovs-ofctl dump-flows s_spine_1 -O OpenFlow13 2>&1 | wc -l

echo "=== STEP 7: POST /iot/mitigate using python urllib (no curl needed) ==="
docker exec sdnshare-controller-1 python3 -c "
import urllib.request, json
req = urllib.request.Request('http://localhost:8080/iot/mitigate',
  data=json.dumps({'src_ip':'10.10.0.99','action':'drop','duration_s':60}).encode(),
  headers={'Content-Type':'application/json'},
  method='POST')
with urllib.request.urlopen(req, timeout=5) as r:
    print('STATUS:', r.status)
    print('BODY:', r.read().decode())
" 2>&1

sleep 2

echo "=== STEP 8: post-mitigation flows (look for priority=200) ==="
docker exec sdnshare-mininet-1 ovs-ofctl dump-flows s_spine_1 -O OpenFlow13 2>&1 | grep -E 'priority=200|priority=250|nw_src' | head -10

echo "=== STEP 9: GET /iot/status ==="
docker exec sdnshare-controller-1 python3 -c "
import urllib.request
with urllib.request.urlopen('http://localhost:8080/iot/status', timeout=5) as r:
    print(r.read().decode())
" 2>&1

echo "=== DONE ==="
