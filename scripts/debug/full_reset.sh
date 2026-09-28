#!/bin/bash
set +e
cd /home/ubuntu/iot-sdn-ai

echo "=== Full down ==="
docker compose -f SdnShare/docker-compose.yaml -f docker-compose.override.yaml down 2>&1 | tail -3

echo "=== Full up ==="
docker compose -f SdnShare/docker-compose.yaml -f docker-compose.override.yaml up -d 2>&1 | tail -3
sleep 12

echo "=== Status ==="
docker ps --format '{{.Names}} {{.Status}}'

echo "=== Launch topo ==="
docker exec sdnshare-mininet-1 mn -c 2>&1 | tail -1
docker exec -d sdnshare-mininet-1 bash -c \
  "python3 /root/iot/topology/mn_iot_topo.py /root/iot/topology/network_config.iot.yaml --no-cli > /tmp/topo5.log 2>&1"
sleep 50

echo "=== Verify dpids unique ==="
for s in $(docker exec sdnshare-mininet-1 ovs-vsctl list-br); do
  dpid=$(docker exec sdnshare-mininet-1 ovs-vsctl get bridge $s datapath_id | tr -d '"')
  echo "  $s : $dpid"
done

echo "=== Controller log (dpids seen) ==="
docker logs sdnshare-controller-1 2>&1 | grep "table-miss instalada" | sort -u | tail -15

echo "=== First pingall (5 pairs) ==="
ATK_PID=$(docker exec sdnshare-mininet-1 pgrep -f "bash --norc --noediting -is mininet:attacker" | head -1)
for target in 10.10.0.10 10.10.0.11 10.10.0.12 10.10.1.10 10.10.0.99; do
  echo "  ping → $target:"
  docker exec sdnshare-mininet-1 mnexec -a $ATK_PID ping -c1 -W2 $target 2>&1 | grep -E "1 received|0 received|unreachable" | head -1
done

echo "=== Flows installed after pings ==="
for s in s_spine_1 s_iot_1; do
  count=$(docker exec sdnshare-mininet-1 ovs-ofctl dump-flows $s -O OpenFlow13 | wc -l)
  echo "  $s: $count flow lines"
done
