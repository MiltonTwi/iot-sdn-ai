#!/bin/bash
echo "=== sleep 20s for L2 settle ==="
sleep 20

echo "=== Flows on s_spine_1 ==="
docker exec sdnshare-mininet-1 ovs-ofctl dump-flows s_spine_1 -O OpenFlow13 | head -15

echo ""
echo "=== Flows on s_iot_1 (leaf) ==="
docker exec sdnshare-mininet-1 ovs-ofctl dump-flows s_iot_1 -O OpenFlow13 | head -15

echo ""
echo "=== Controller recent logs ==="
docker logs sdnshare-controller-1 2>&1 | tail -15

echo ""
echo "=== Ping retry ==="
ATK_PID=$(docker exec sdnshare-mininet-1 pgrep -f "bash --norc --noediting -is mininet:attacker" | head -1)
docker exec sdnshare-mininet-1 mnexec -a $ATK_PID ping -c2 -W2 10.10.0.12 2>&1 | tail -3

echo ""
echo "=== Flows on spine after ping attempt ==="
docker exec sdnshare-mininet-1 ovs-ofctl dump-flows s_spine_1 -O OpenFlow13 | grep -v table-miss | head -10
