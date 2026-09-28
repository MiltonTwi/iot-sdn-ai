#!/usr/bin/env bash
# Repite el experimento de lazo cerrado N veces (r2..rN; r1 = corrida original).
#   bash scripts/closed_loop_reps.sh 5
set -u
cd "$(dirname "$0")/.."
N=${1:-5}
for i in $(seq 2 "$N"); do
  echo "=== repeticion $i/$N $(date +%T)"
  python3 -u ml_extra/closed_loop_eval.py --benign-s 120 --attack-s 30 --out "closed_loop_r$i.json" \
    && (cd ml_extra && python3 closed_loop_rescore.py "closed_loop_r$i.json" | tail -12)
done
echo "=== FIN $(date +%T)"
