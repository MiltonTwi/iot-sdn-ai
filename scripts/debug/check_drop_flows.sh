#!/bin/bash
echo "=== Drop rules across ALL switches ==="
for s in $(docker exec sdnshare-mininet-1 ovs-vsctl list-br); do
  count=$(docker exec sdnshare-mininet-1 ovs-ofctl dump-flows $s -O OpenFlow13 2>&1 | grep -c "priority=200")
  echo "$s: $count drop flows"
  docker exec sdnshare-mininet-1 ovs-ofctl dump-flows $s -O OpenFlow13 2>&1 | grep "priority=200" | head -2
done
