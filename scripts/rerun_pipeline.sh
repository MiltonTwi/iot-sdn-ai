#!/usr/bin/env bash
# Re-corrida corregida. Arregla 4 bugs de plumbing:
#  1) formato: tcpdump escribe pcap CLASICO (tshark default = pcapng, ilegible)
#  2) 9p 2GB: extractor corre DENTRO del container sobre pcap local; solo el CSV
#     (chico) va al mount. El pcap gigante nunca cruza 9p.
#  3) manifests: se copian desde /tmp del CONTAINER (no de la VM) a data/raw.
#  4) snaplen -s96 (headers) + flow_extractor usa orig_len -> features de tamano ok.
#
# Modo:  MODE=smoke  -> 3 ataques cortos (DUR=8), sin train/report (~2 min)
#        MODE=full   -> 14 ataques con durations del catalogo + train + report
set -o pipefail
cd /home/ubuntu/iot-sdn-ai || exit 9
CTN=sdnshare-mininet-1
# Captura via port-mirror en s_iot_0 (donde cuelgan atacante + servers).
# El spine NO ve el trafico intra-zona-0; el mirror sobre s_iot_0 ve ataques
# (attacker->servers) + benigno (IoT de zonas 1-7 -> servers).
BR=s_iot_0
MON=mon0
IFACE="$MON"
MODE="${MODE:-full}"

RUN=run_$(date +%Y%m%d-%H%M%S)
[ "$MODE" = smoke ] && RUN="smoke_$RUN"
echo "RUN=$RUN  MODE=$MODE" | tee /home/ubuntu/last_run.txt
mkdir -p /home/ubuntu/iot_run "data/raw/$RUN" "data/processed/$RUN"
LOG="/home/ubuntu/iot_run/$RUN.log"
PCAP="/root/cap_$RUN.pcap"

dexec(){ docker exec "$CTN" bash -lc "$1"; }
cleanup(){ docker exec "$CTN" pkill -f tcpdump >/dev/null 2>&1 || true; docker exec "$CTN" bash -lc "bash /root/iot/pipeline/mirror.sh teardown $BR $MON" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# ── Episodios ────────────────────────────────────────────────────────────────
# Cada escenario corre EPISODES veces (duración catálogo / EPISODES, mín 20s),
# intensidad aleatorizada por episodio (runner --episode) y fuente rotando entre
# el attacker y dispositivos IoT comprometidos de zonas 4-7 (no son bots de
# mirai_coordinated ni objetivos de scan/bruteforce, que apuntan a zonas 1-3).
# Rondas intercaladas: ep1 de todos, ep2 de todos... → episodios de una misma
# clase separados en el tiempo. Cada episodio = 1 grupo en la CV anti-fuga.
EPISODES="${EPISODES:-5}"
SOURCES=(attacker parkinga fitnessba weatherst beacona)
SCENARIOS=(syn_flood udp_flood icmp_flood http_flood slowloris port_scan
           dns_amplification coap_amplification ssdp_amplification
           mqtt_subscribe_flood mqtt_malformed credential_bruteforce mirai_coordinated)
COOLDOWN="${COOLDOWN:-10}"
WARMUP="${WARMUP:-120}"

cat_duration(){  # duración base del escenario en catalog.yaml
  python3 -c "import yaml,sys;c=yaml.safe_load(open('iot/attacks/catalog.yaml'));print(next(s['duration_s'] for s in c['scenarios'] if s['id']==sys.argv[1]))" "$1"
}

launch(){  # launch <src_host> <scenario> <dur> <episode>
  docker exec "$CTN" bash -c "PID=\$(pgrep -f 'is mininet:$1\$' | head -1); [ -n \"\$PID\" ] || { echo 'host $1 no encontrado'; exit 1; }; mnexec -a \$PID python3 /root/iot/attacks/runner.py --scenario $2 --duration $3 --episode $4"
}

run_episodes(){
  echo ">>> warmup benigno ${WARMUP}s (sin ataques)"; sleep "$WARMUP"
  local r s d src i=0
  for r in $(seq 1 "$EPISODES"); do
    for s in "${SCENARIOS[@]}"; do
      d=$(cat_duration "$s"); d=$(( d / EPISODES )); [ "$d" -lt 20 ] && d=20
      src=${SOURCES[$(( i % ${#SOURCES[@]} ))]}; i=$((i + 1))
      # scan/bruteforce apuntan a zonas 1-3: desde un bot de zona 4-7 ese
      # tráfico no toca s_iot_0 (punto de captura) → siempre desde attacker.
      case "$s" in port_scan|credential_bruteforce) src=attacker ;; esac
      echo ">>> [ronda $r/$EPISODES] $s  src=$src  dur=${d}s"
      launch "$src" "$s" "$d" "$r" || echo ">>> WARN $s ep$r rc=$?"
      sleep "$COOLDOWN"
    done
  done
  # ARP_SPOOF: 1 episodio desde attacker (clase aún excluida, pega #4)
  echo ">>> arp_spoof (1 episodio)"; launch attacker arp_spoof 60 1 || true
}

run_all() {
  echo ">>> STAGE cleanup (manifests viejos + pcaps)"
  dexec "rm -f /tmp/attack_*.json ${PCAP}" || true
  docker exec "$CTN" pkill -f tcpdump 2>/dev/null || true
  sleep 1

  echo ">>> STAGE mirror_setup"
  dexec "bash /root/iot/pipeline/mirror.sh setup $BR $MON"

  echo ">>> STAGE capture_start"
  # tcpdump = pcap CLASICO, snaplen 96 (solo headers), a FS local del container
  docker exec -d "$CTN" tcpdump -i "$IFACE" -s 96 -w "$PCAP"
  sleep 3
  if ! docker exec "$CTN" pgrep -f "tcpdump.*$IFACE" >/dev/null; then
    echo ">>> ERROR tcpdump no arranco"; return 3
  fi

  echo ">>> STAGE attacks_start ($MODE)"
  if [ "$MODE" = smoke ]; then
    # mismo camino que full: fuentes rotadas + episodios (bot IoT incluido)
    launch attacker  syn_flood         8 1 || true; sleep 5
    launch parkinga  http_flood        8 1 || true; sleep 5
    launch fitnessba http_flood        8 2 || true; sleep 5
    launch weatherst dns_amplification 8 1 || true; sleep 5
    launch attacker  port_scan         8 1 || true; sleep 5
  else
    run_episodes
  fi

  echo ">>> STAGE attacks_done (drain 8s)"; sleep 8
  echo ">>> STAGE capture_stop"
  docker exec "$CTN" pkill -f tcpdump 2>/dev/null || true
  sleep 2
  dexec "bash /root/iot/pipeline/mirror.sh teardown $BR $MON" || true
  local psz
  psz=$(docker exec "$CTN" stat -c%s "$PCAP" 2>/dev/null || echo 0)
  echo ">>> pcap_bytes=$psz (local container fs)"
  [ "$psz" -lt 20000 ] && { echo ">>> ERROR pcap chico ($psz)"; return 4; }

  echo ">>> STAGE manifests_copy"
  dexec "mkdir -p /root/data/raw/$RUN && cp /tmp/attack_*.json /root/data/raw/$RUN/ 2>/dev/null; ls /root/data/raw/$RUN/attack_*.json | wc -l"

  # TODO el pipeline corre en FS LOCAL del contenedor (/root), NO en el mount 9p:
  # el mount trunca archivos a 2 GiB y con 11M+ flujos los CSV intermedios lo
  # superan (flows_labeled dio I/O error a 2 GiB). Solo el dataset final capado
  # (chico) se copia al mount. Si algo falla, el pcap se CONSERVA.
  local LF="/root/flows_$RUN.csv" LL="/root/lbl_$RUN.csv" LD="/root/ds_$RUN.csv"
  echo ">>> STAGE extract (pcap -> flows local)"
  dexec "python3 /root/iot/pipeline/flow_extractor.py --pcap $PCAP --out $LF" \
    || { echo ">>> ERROR extract (pcap conservado: $PCAP)"; return 5; }
  # flujos extraidos → el pcap ya no hace falta (libera ~10 GB antes del sort)
  docker exec "$CTN" rm -f "$PCAP" 2>/dev/null || true

  echo ">>> STAGE label (local)"
  dexec "python3 /root/iot/pipeline/label_dataset.py --flows $LF --manifests /root/data/raw/$RUN/ --out $LL" \
    || { echo ">>> ERROR label"; return 6; }
  docker exec "$CTN" rm -f "$LF" 2>/dev/null || true

  echo ">>> STAGE feature (local, sort temp en /root)"
  dexec "TMPDIR=/root python3 /root/iot/pipeline/feature_engineering.py --inp $LL --out $LD" \
    || { echo ">>> ERROR feature"; return 7; }
  docker exec "$CTN" rm -f "$LL" 2>/dev/null || true

  echo ">>> STAGE cap (max ${CAP:-50000} filas/clase; seed 42) — capa en sitio"
  # Cap POST-feature via reservoir sampling. Deja intactas las clases bajo el cap.
  dexec "python3 /root/iot/pipeline/cap_dataset.py $LD ${CAP:-50000}" \
    || { echo ">>> ERROR cap"; return 7; }
  echo ">>> copiando dataset capado al mount"
  dexec "mkdir -p /root/data/processed/$RUN && cp $LD /root/data/processed/$RUN/dataset.csv && rm -f $LD"
  echo ">>> Dataset listo: data/processed/$RUN/dataset.csv"

  echo ">>> STAGE validate (distribucion de labels)"
  python3 - "data/processed/$RUN/dataset.csv" <<'PY'
import csv,sys,collections
rows=list(csv.DictReader(open(sys.argv[1])))
c=collections.Counter(r["label"] for r in rows)
g=collections.defaultdict(set)
for r in rows: g[r["label"]].add(r.get("episode") or r["src_ip"])
print(">>> filas:",len(rows)," clases:",len(c))
for k,v in c.most_common(): print(f">>>   {k:<24}{v:>8}  grupos={len(g[k])}")
PY

  if [ "$MODE" = full ]; then
    if python3 -c "import joblib, sklearn, xgboost" 2>/dev/null; then
      echo ">>> STAGE train"
      make -f Makefile.iot iot-train RUN="$RUN" || return 8
      echo ">>> STAGE report"
      make -f Makefile.iot iot-report RUN="$RUN" || return 9
    else
      echo ">>> SKIP train/report: VM sin deps ML → entrenar en el host (dataset en el mount)"
    fi
  fi
}

run_all 2>&1 | tee "$LOG"
rc=${PIPESTATUS[0]}
echo "PIPELINE_EXIT=$rc" | tee -a "$LOG"
exit "$rc"
