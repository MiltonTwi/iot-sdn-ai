#!/bin/bash
docker exec sdnshare-mininet-1 sh -c 'pkill -9 -f mn_iot_topo 2>/dev/null; pkill -9 -f "mininet:" 2>/dev/null; true' || true
docker exec sdnshare-mininet-1 mn -c 2>&1 | tail -1

docker exec -d sdnshare-mininet-1 bash -c \
  "python3 /root/iot/topology/mn_iot_topo.py /root/iot/topology/network_config.iot.yaml --auto-traffic --no-cli > /tmp/topo_at.log 2>&1"

echo "Waiting 60s for topology + auto-traffic to settle..."
sleep 60

ATK_PID=$(docker exec sdnshare-mininet-1 pgrep -f "bash --norc --noediting -is mininet:attacker" | head -1)
echo "ATK_PID=$ATK_PID"

echo ""
echo "=== Ping tests ==="
for target in 10.10.0.10 10.10.0.11 10.10.0.12 10.10.1.10; do
  result=$(docker exec sdnshare-mininet-1 mnexec -a $ATK_PID ping -c2 -W3 $target 2>&1 | grep -E "received" | head -1)
  echo "  → $target: $result"
done

echo ""
echo "=== Flows on spine_1 (after pings) ==="
docker exec sdnshare-mininet-1 ovs-ofctl dump-flows s_spine_1 -O OpenFlow13 2>&1 | head -8

echo ""
echo "=== Flows count per switch ==="
for s in $(docker exec sdnshare-mininet-1 ovs-vsctl list-br); do
  c=$(docker exec sdnshare-mininet-1 ovs-ofctl dump-flows $s -O OpenFlow13 2>&1 | wc -l)
  echo "  $s: $c lines"
done
