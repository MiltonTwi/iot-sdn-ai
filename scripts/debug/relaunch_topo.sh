#!/bin/bash
set -e
echo "=== STEP 1: tear down old topology ==="
docker exec sdnshare-mininet-1 sh -c "pkill -9 -f mn_iot_topo 2>/dev/null; pkill -9 -f 'mininet:' 2>/dev/null; true" || true
docker exec sdnshare-mininet-1 mn -c 2>&1 | tail -2

echo "=== STEP 2: restart controller to clear DPSet state ==="
docker restart sdnshare-controller-1 > /dev/null
sleep 8
echo "controller ready"

echo "=== STEP 3: launch topology with unique dpids ==="
docker exec -d sdnshare-mininet-1 bash -c \
  "python3 /root/iot/topology/mn_iot_topo.py /root/iot/topology/network_config.iot.yaml --no-cli > /tmp/topo4.log 2>&1"
sleep 45

echo "=== STEP 4: verify dpid mapping (unique?) ==="
for s in $(docker exec sdnshare-mininet-1 ovs-vsctl list-br); do
  dpid=$(docker exec sdnshare-mininet-1 ovs-vsctl get bridge $s datapath_id | tr -d '"')
  echo "  $s : $dpid"
done

echo "=== STEP 5: controller seen dpids ==="
docker logs sdnshare-controller-1 2>&1 | grep -oE "dpid=[0-9]+" | sort -u

echo "=== STEP 6: ping test ==="
ATK_PID=$(docker exec sdnshare-mininet-1 pgrep -f "bash --norc --noediting -is mininet:attacker" | head -1)
echo "ATK_PID=$ATK_PID"
docker exec sdnshare-mininet-1 mnexec -a $ATK_PID ping -c3 -W3 10.10.0.12 2>&1 | tail -4
