#!/bin/bash
echo "=== controller listening ports ==="
docker exec sdnshare-controller-1 ss -tn -l 2>&1 | head -10
echo ""
echo "=== mininet -> controller connections ==="
docker exec sdnshare-mininet-1 ss -tn 2>&1 | grep 6633 | head -20
echo ""
echo "=== switch s_iot_0 detail ==="
docker exec sdnshare-mininet-1 ovs-vsctl show | head -40
