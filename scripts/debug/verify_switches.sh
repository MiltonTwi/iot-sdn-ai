#!/bin/bash
echo "=== bridges ==="
docker exec sdnshare-mininet-1 ovs-vsctl list-br
echo ""
echo "=== controller per bridge ==="
for s in $(docker exec sdnshare-mininet-1 ovs-vsctl list-br); do
  ctrl=$(docker exec sdnshare-mininet-1 ovs-vsctl get-controller $s)
  conn=$(docker exec sdnshare-mininet-1 ovs-vsctl find Controller target=$ctrl | grep is_connected | head -1)
  echo "$s -> $ctrl   $conn"
done
echo ""
echo "=== controller fail mode ==="
for s in $(docker exec sdnshare-mininet-1 ovs-vsctl list-br); do
  fm=$(docker exec sdnshare-mininet-1 ovs-vsctl get-fail-mode $s)
  echo "$s fail_mode=$fm"
done
