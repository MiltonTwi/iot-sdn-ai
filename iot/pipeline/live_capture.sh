#!/usr/bin/env bash
# Captura en vivo por ventanas para el lazo cerrado detector → controlador.
# Corre DENTRO del contenedor mininet.
#
#   tcpdump (mon0) ─pipe─▶ flow_extractor --live (estado de flujos persistente;
#     cada CHUNK s escribe snapshot acumulado de los flujos activos)
#   ─▶ feature_engineering ─▶ /root/data/live/feat_<ts>.csv
#   (lo consume ml_extra/live_detector.py en la VM)
#
# uso: live_capture.sh start [CHUNK_S]  |  live_capture.sh stop
# Mismo punto de captura y formato que el dataset (mirror ingress en s_iot_0,
# pcap clásico -s 96). El extractor persistente conserva la duración real de
# las conexiones largas (slowloris, MQTT) en vez de truncarlas a la ventana.
set -u
BR=s_iot_0; MON=mon0
MAX_ROWS=${LIVE_MAX_ROWS:-20000}  # = MAX_ROWS de ml_extra/live_detector.py
SPAN=${LIVE_SPAN:-5}  # s de actividad por snapshot = ventana de las features host_*/dst_*_5s
WORK=/root/live_work
OUT=/root/data/live
HERE=$(cd "$(dirname "$0")" && pwd)

stop() {
  pkill -f "tcpdump -i $MON" 2>/dev/null || true
  pkill -f "flow_extractor.py --live-dir" 2>/dev/null || true
  pkill -f "live_capture.sh loop" 2>/dev/null || true
  bash "$HERE/mirror.sh" teardown "$BR" "$MON" >/dev/null 2>&1 || true
  echo "live capture detenida"
}

process() {  # snapshot de flujos cerrado → CSV de features (escritura atómica)
  local flows="$1" ts feat
  ts=$(basename "$flows" .csv); ts=${ts#flows_}
  feat="$WORK/feat_$ts.csv"
  local t0=$SECONDS n
  if TMPDIR=$WORK python3 "$HERE/feature_engineering.py" --inp "$flows" --out "$feat" >/dev/null 2>&1; then
    # Muestreo DESPUÉS de las features (las host_*/dst_* ya se calcularon con todos
    # los flujos) y ANTES de cruzar el montaje sshfs: bajo flood el CSV completo
    # (cientos de miles de filas) tardaba segundos en copiarse y en leerse.
    n=$(($(wc -l < "$feat") - 1))
    if [ "$n" -gt "$MAX_ROWS" ]; then
      { head -1 "$feat"; tail -n +2 "$feat" | shuf -n "$MAX_ROWS"; } > "$feat.s" && mv "$feat.s" "$feat"
    fi
    # cp + mv -T: sshfs no deja preservar owner con mv entre FS
    cp "$feat" "$OUT/.feat_$ts.tmp" && mv -T "$OUT/.feat_$ts.tmp" "$OUT/feat_$ts.csv" 2>/dev/null
    echo "WIN $ts flows=$n t=$((SECONDS - t0))s"
  else
    echo "WARN ventana $ts falló" >&2
  fi
  rm -f "$flows" "$feat"
}

loop() {
  # Tiempo real: si se acumulan varias ventanas se procesa solo la más reciente
  # y las atrasadas se descartan (un veredicto viejo no sirve para mitigar).
  while true; do
    mapfile -t wins < <(ls -1 "$WORK"/flows_*.csv 2>/dev/null | sort)
    n=${#wins[@]}
    if [ "$n" -gt 0 ]; then
      for ((i = 0; i < n - 1; i++)); do
        echo "SKIP $(basename "${wins[$i]}") (atrasada)"; rm -f "${wins[$i]}"
      done
      process "${wins[$((n - 1))]}"
    fi
    sleep 0.2
  done
}

case "${1:-}" in
  start)
    CHUNK="${2:-2}"
    stop >/dev/null
    mkdir -p "$WORK" "$OUT"; rm -f "$WORK"/* "$WORK"/.flows.tmp "$OUT"/feat_*.csv
    bash "$HERE/mirror.sh" setup "$BR" "$MON"
    # -U: vuelca cada paquete al pipe sin esperar a llenar el buffer.
    # Si el extractor no da abasto, el kernel descarta en tcpdump (muestreo natural).
    setsid nohup bash -c "tcpdump -i $MON -s 96 -U -w - 2>/root/live_tcpdump.log \
      | python3 $HERE/flow_extractor.py --live-dir $WORK --emit-every $CHUNK --span $SPAN" \
      > /root/live_extractor.log 2>&1 &
    setsid nohup bash "$0" loop > /root/live_capture.log 2>&1 &
    echo "live capture: ventana=${CHUNK}s → $OUT"
    ;;
  loop) loop ;;
  stop) stop ;;
  *) echo "uso: $0 start [chunk_s] | stop"; exit 2 ;;
esac
