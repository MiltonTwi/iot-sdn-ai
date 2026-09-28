#!/bin/bash
echo "=== Bridge to dpid mapping ==="
for s in $(docker exec sdnshare-mininet-1 ovs-vsctl list-br); do
  dpid_hex=$(docker exec sdnshare-mininet-1 ovs-vsctl get bridge $s datapath_id | tr -d '"')
  dpid_dec=$(printf "%d\n" "0x$dpid_hex" 2>/dev/null)
  echo "$s : hex=$dpid_hex dec=$dpid_dec"
done

echo ""
echo "=== Re-trigger mitigate and immediately dump flows on all switches ==="
docker exec sdnshare-controller-1 python3 -c "
import urllib.request, json
req = urllib.request.Request('http://localhost:8080/iot/mitigate',
  data=json.dumps({'src_ip':'10.10.0.99','action':'drop','duration_s':120}).encode(),
  headers={'Content-Type':'application/json'},
  method='POST')
with urllib.request.urlopen(req, timeout=5) as r:
    print('STATUS:', r.status); print('BODY:', r.read().decode())
"

sleep 1

echo ""
echo "=== Per-bridge: ALL flows (any priority) ==="
for s in $(docker exec sdnshare-mininet-1 ovs-vsctl list-br); do
  total=$(docker exec sdnshare-mininet-1 ovs-ofctl dump-flows $s -O OpenFlow13 2>&1 | wc -l)
  drop_count=$(docker exec sdnshare-mininet-1 ovs-ofctl dump-flows $s -O OpenFlow13 2>&1 | grep -c "priority=200")
  echo "$s: total_lines=$total drop_count=$drop_count"
done

echo ""
echo "=== Detail on spine_1 (any flow with 10.10.0.99) ==="
docker exec sdnshare-mininet-1 ovs-ofctl dump-flows s_spine_1 -O OpenFlow13 | grep -E "10\.10\.0\.99|priority=200" | head -5
