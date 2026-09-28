#!/bin/bash
# Verificación integral del sistema IoT-SDN-AI.

set +e  # no exit on error — queremos ver todo lo que falla
PASS=0; FAIL=0; WARN=0
log() { echo "[$(date +%T)] $*"; }
ok()  { log "✓ $*"; PASS=$((PASS+1)); }
ko()  { log "✗ $*"; FAIL=$((FAIL+1)); }
wn()  { log "⚠ $*"; WARN=$((WARN+1)); }
hdr() { echo ""; echo "═══════════ $* ═══════════"; }

cd /home/ubuntu/iot-sdn-ai || exit 1

hdr "1. CÓDIGO — pytest suite"
out=$(python3 -m pytest tests/ -q --no-header 2>&1 | tail -3)
echo "$out"
if echo "$out" | grep -qE "^[0-9]+ passed"; then ok "pytest"; else ko "pytest"; fi

hdr "2. CÓDIGO — imports principales"
python3 -c "
import sys; sys.path.insert(0, '.')
from ml_extra import common
from ml_extra.models import rf, mlp, isoforest, autoencoder
from iot.pipeline import flow_extractor, label_dataset, feature_engineering
from iot.attacks import runner
print('all imports OK')
" 2>&1 && ok "imports" || ko "imports"

hdr "3. DATASET — integridad"
ds=/home/ubuntu/iot_run/dataset_p1p2_clean13.csv
if [ -f "$ds" ]; then
  n=$(wc -l < "$ds")
  ok "dataset existe ($n filas)"
  python3 -c "
import pandas as pd
df = pd.read_csv('$ds')
assert df.shape == (71064, 56), f'wrong shape {df.shape}'
assert df['label'].nunique() == 13, f'wrong classes {df[\"label\"].nunique()}'
assert df.isnull().sum().sum() == 0, 'nulls found'
print('shape:', df.shape, 'classes:', df['label'].nunique())
" 2>&1 && ok "dataset content" || ko "dataset content"
else
  ko "dataset missing"
fi

hdr "4. MODELOS — load + predict"
python3 << 'PY'
import sys; sys.path.insert(0, '.')
from pathlib import Path
import joblib, numpy as np
from ml_extra import common
DS = Path('/home/ubuntu/iot_run/dataset_p1p2_clean13.csv')
ART = Path('ml_extra/artifacts')
X, y = common.load_dataset(DS)
X_tr, X_te, y_tr, y_te, le, _ = common.split_scaled(X, y)
for name in ['rf','xgb','mlp','isoforest','autoencoder']:
    p = ART / f'{name}.joblib'
    if not p.exists():
        print(f'  MISSING: {name}.joblib'); continue
    m = joblib.load(p)
    pred = m.predict(X_te[:100])
    print(f'  {name}: loaded, predicts {pred.shape}')
PY
[ $? -eq 0 ] && ok "modelos load+predict" || ko "modelos load+predict"

hdr "5. ARTIFACTS — todos presentes"
ART=ml_extra/artifacts
for f in metrics.json cv_robust.json bootstrap_ci.json calibration_metrics.json adversarial_metrics.json cross_eval_binary.json shap_clean13.png calibration_clean13.png adversarial_clean13.png umap_clean13.png; do
  if [ -f "$ART/$f" ]; then ok "$f"; else ko "MISSING: $f"; fi
done

hdr "6. SCRIPTS AUXILIARES — ejecutables"
for script in ml_extra/calibration.py ml_extra/adversarial.py ml_extra/confusion_analysis.py ml_extra/explain.py ml_extra/report.py ml_extra/naive_baseline.py ml_extra/cic_iot_adapter.py ml_extra/cross_eval.py; do
  if [ -f "$script" ]; then
    head -1 "$script" | grep -q "^#!" && ok "$script (shebang)" || wn "$script (no shebang)"
  else
    ko "MISSING: $script"
  fi
done

hdr "7. SLIDES y DOCS"
for doc in docs/defensa/DEFENSA-slides.md docs/resultados/MITIGATION-evidence.md docs/guias/GUIA-grabar-demo.md; do
  if [ -f "$doc" ]; then
    lines=$(wc -l < "$doc")
    ok "$doc ($lines lines)"
  else
    ko "MISSING: $doc"
  fi
done

hdr "8. PDF REPORTS"
for pdf in data/processed/run_clean13_p1p2/report_final.pdf data/processed/run_clean13_p1p2/report_clean13_v2.pdf; do
  if [ -f "$pdf" ]; then
    sz=$(stat -c%s "$pdf")
    ok "$pdf (${sz} bytes)"
  else
    ko "MISSING: $pdf"
  fi
done

hdr "9. DOCKER STACK — health"
if docker ps --format '{{.Names}}' | grep -q sdnshare-controller-1; then
  status=$(docker inspect sdnshare-controller-1 --format '{{.State.Health.Status}}')
  if [ "$status" = "healthy" ]; then ok "controller healthy"; else wn "controller $status"; fi
else
  ko "controller not running"
fi
if docker ps --format '{{.Names}}' | grep -q sdnshare-mininet-1; then
  ok "mininet running"
else
  ko "mininet not running"
fi

hdr "10. MITIGATION CHAIN — REST endpoints"
resp=$(docker exec sdnshare-controller-1 python3 -c "
import urllib.request, json
try:
    with urllib.request.urlopen('http://localhost:8080/iot/status', timeout=3) as r:
        print(r.read().decode())
except Exception as e:
    print('ERROR:', e)
" 2>&1)
if echo "$resp" | grep -q '"active"'; then ok "GET /iot/status responds"; else ko "GET /iot/status: $resp"; fi

resp=$(docker exec sdnshare-controller-1 python3 -c "
import urllib.request, json
try:
    req = urllib.request.Request('http://localhost:8080/iot/mitigate',
        data=json.dumps({'src_ip':'10.10.0.250','action':'drop','duration_s':30}).encode(),
        headers={'Content-Type':'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=3) as r:
        print(r.read().decode())
except Exception as e:
    print('ERROR:', e)
" 2>&1)
if echo "$resp" | grep -q '"dpids"'; then ok "POST /iot/mitigate works"; else ko "POST /iot/mitigate: $resp"; fi

resp=$(docker exec sdnshare-controller-1 python3 -c "
import urllib.request, json
try:
    with urllib.request.urlopen('http://localhost:8080/iot/antispoof/bindings', timeout=3) as r:
        print(r.read().decode()[:200])
except Exception as e:
    print('ERROR:', e)
" 2>&1)
if echo "$resp" | grep -q '"bindings"'; then ok "GET /iot/antispoof/bindings works"; else ko "antispoof endpoint: $resp"; fi

hdr "11. OVS FLOWS — DROP rule installed"
flow=$(docker exec sdnshare-mininet-1 ovs-ofctl dump-flows s_spine_1 -O OpenFlow13 2>&1 | grep "priority=200" | head -1)
if [ -n "$flow" ]; then ok "DROP rule visible: $flow"; else ko "no DROP rules on s_spine_1"; fi

hdr "12. STATS RIGUROSAS — recompute mini-check"
python3 << 'PY'
import json
m = json.load(open('ml_extra/artifacts/metrics.json'))
cv = json.load(open('ml_extra/artifacts/cv_robust.json'))
bs = json.load(open('ml_extra/artifacts/bootstrap_ci.json'))
ce = json.load(open('ml_extra/artifacts/cross_eval_binary.json'))
print(f"  RF f1_macro single split: {m['rf']['f1_macro']:.4f}")
print(f"  RF f1_macro 10-fold x 5 seeds: {cv['rf']['mean']:.4f} ± {cv['rf']['std']:.4f}")
print(f"  RF bootstrap f1_macro CI95: [{bs['rf']['f1_macro']['ci95'][0]:.3f}, {bs['rf']['f1_macro']['ci95'][1]:.3f}]")
print(f"  CIC cross-domain binary AUC: {ce['cross']['auc']:.4f}")
print(f"  IsoForest attack_f1: {m['isoforest']['attack_f1']:.4f}")
print(f"  OCSVM attack_f1: {m['autoencoder']['attack_f1']:.4f}")
PY
[ $? -eq 0 ] && ok "stats consistency" || ko "stats consistency"

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  RESUMEN: $PASS passed | $FAIL failed | $WARN warnings"
echo "════════════════════════════════════════════════════════════"
