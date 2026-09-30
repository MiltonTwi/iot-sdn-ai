#!/usr/bin/env bash
# Repite el experimento de lazo cerrado y re-puntúa cada corrida.
#   bash scripts/closed_loop_reps.sh N [PRIMERA]      (defaults: 5, 2 → r2..rN; r1 = corrida original)
# Variables: CHUNK (ventana en vivo, s; 5), PREFIX (closed_loop_r), BENIGN_S (120),
#   COOLDOWN (pausa entre escenarios, s; 20 — usar ≥ 60 para evitar arrastre del ataque previo)
set -u
cd "$(dirname "$0")/.."
N=${1:-5}; FIRST=${2:-2}
CHUNK=${CHUNK:-5}; PREFIX=${PREFIX:-closed_loop_r}; BENIGN_S=${BENIGN_S:-120}; COOLDOWN=${COOLDOWN:-20}
for i in $(seq "$FIRST" "$N"); do
  echo "=== repeticion $i/$N chunk=${CHUNK}s $(date +%T)"
  python3 -u ml_extra/closed_loop_eval.py --benign-s "$BENIGN_S" --attack-s 30 --chunk-s "$CHUNK" --cooldown-s "$COOLDOWN" \
    --out "${PREFIX}$i.json" \
    && (cd ml_extra && python3 closed_loop_rescore.py "${PREFIX}$i.json" | tail -12)
done
echo "=== FIN $(date +%T)"
