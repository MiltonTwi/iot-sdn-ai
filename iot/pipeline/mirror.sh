#!/usr/bin/env bash
# Port-mirroring OVS para capturar TODO el trafico que cruza un bridge.
# uso: mirror.sh setup [bridge] [mon]  |  mirror.sh teardown [bridge] [mon]
# Mirror ingress-only (select-src-port) -> cada paquete se copia UNA vez.
set -e
act="$1"; BR="${2:-s_iot_0}"; MON="${3:-mon0}"

teardown() {
  ovs-vsctl --if-exists clear Bridge "$BR" mirrors >/dev/null 2>&1 || true
  ovs-vsctl --if-exists del-port "$BR" "$MON" >/dev/null 2>&1 || true
}

if [ "$act" = setup ]; then
  teardown
  ovs-vsctl add-port "$BR" "$MON" -- set interface "$MON" type=internal
  ip link set "$MON" up
  ids=""; refs=""; i=0
  for p in $(ovs-vsctl list-ports "$BR"); do
    [ "$p" = "$MON" ] && continue
    ids="$ids -- --id=@p$i get Port $p"; refs="$refs,@p$i"; i=$((i+1))
  done
  refs="${refs#,}"
  eval ovs-vsctl $ids -- --id=@mon get Port "$MON" \
    -- --id=@m create Mirror name=m0 select-src-port="[$refs]" output-port=@mon \
    -- set Bridge "$BR" mirrors=@m
  echo "mirror setup: $i puertos espejados -> $MON en $BR"
elif [ "$act" = teardown ]; then
  teardown
  echo "mirror teardown ok ($BR/$MON)"
else
  echo "uso: mirror.sh setup|teardown [bridge] [mon]"; exit 2
fi
