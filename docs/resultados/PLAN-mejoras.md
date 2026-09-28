# Plan de trabajo — corrección de rigor y amplificación

**Creado:** 2026-09-22 · **Baseline:** `run_20260921-135634` (RF acc 0.973 / F1-macro 0.822)
**Dónde corre:** código se edita en host Windows; pipeline/entrenamiento en **VM** (`/home/ubuntu/iot-sdn-ai`, contenedor `sdnshare-mininet-1`). El host no tiene pandas.

## Objetivo
Métricas honestas y defendibles ante jurado. Dos huecos críticos: (1) fuga train/test infla los floods a F1 1.00; (2) amplificación no se capturó (recall ~0). El relato de tesis se fortalece documentando el **delta antes/después** de cada corrección, no ocultándolo.

---

## FASE 0 — Congelar baseline · [x] HECHO
Preserva la corrida actual como "baseline optimista" para la tabla antes/después.
- `cp ml_extra/artifacts/metrics.json ml_extra/artifacts/metrics_baseline_leaky.json`
- `cp ml_extra/artifacts/report_run_20260921-135634.pdf ml_extra/artifacts/report_baseline_leaky.pdf`
- Anotar en tabla: acc, F1-macro, y F1 por clase de los 5 modelos.
**Aceptación:** archivos baseline guardados, tabla inicial en este doc.

## FASE 1 — Eliminar fuga train/test · [x] HECHO (ver Resultados)
**Problema:** `common.split_scaled` usa `train_test_split(shuffle=True, stratify)`. Los floods son casi-duplicados (MIRAI 50k filas / 191 firmas; UDP 23k / 134; SYN 50k / 429) → la misma firma cae en train y test → F1=1.00 es memorización.
**Fix (pragmático):** split por grupo con `StratifiedGroupKFold`, grupo = firma `(src_ip, dst_ip, dst_port, proto)`. Firmas idénticas no cruzan la frontera. Estratificado para no perder clases raras en test.
- Editar `ml_extra/common.py`: nueva función `split_grouped(X, y, groups, ...)` que devuelva el mismo contrato `(X_tr_s, X_te_s, y_tr, y_te, le, scaler)`.
- `load_dataset` debe devolver también la columna de firma (grupo) sin meterla como feature.
- Parámetro en `train_all.py`: `--split {stratified,grouped}` (default `grouped`).
- **Complemento opcional (más honesto aún):** dedup de firmas exactas antes del split + feature de conteo. Documentar cuál se usó.
**Re-entrenar (VM):** `make -f Makefile.iot iot-train RUN=run_20260921-135634` (no requiere re-correr la red; ~1-2 min).
**Aceptación:** F1 de floods **baja** de 1.00 (es el resultado correcto). Registrar nuevo acc/F1-macro. Esperado: acc 0.97 → ~0.85-0.92.
**Riesgo:** números bajan. Es lo buscado; se documenta como corrección de leakage.

## FASE 2 — Amplificación + DIVERSIDAD · [~] CÓDIGO LISTO, falta re-run VM
**Problema:** las 3 clases amplificación tienen `tot_bwd_bytes=0`, `down_up_ratio=0`, `tot_pkts≈1`, `src_uni=1-2`. La respuesta reflejada (que DEFINE el ataque) nunca se capturó, y el spoofing de 254 víctimas colapsó a 1-2 flujos. Sin señal, recall≈0 es inevitable — no es problema de modelo.
**Diagnóstico (VM, aislar 1 escenario):**
1. Lanzar solo DNS amp: `make -f Makefile.iot iot-attack SCN=dns_amplification DUR=30`
2. `tcpdump` en el **atacante**: ¿salen paquetes con source spoofeado (10.10.1.x variando) o todos con IP real? → valida hipótesis (a) spoofing falla / anti-spoof dropea.
3. `tcpdump` en el **reflector** (10.10.0.13): ¿responde a la query cruda? → hipótesis (b) server rechaza query malformada.
4. `tcpdump` en la **víctima** (10.10.1.10) y en `mon0`: ¿el mirror de `s_iot_0` ve la respuesta reflector→víctima (egresa a zonas 1-7 vía spine)? → hipótesis (c) captura/etiquetado.
**Correcciones según causa:**
- (a) Si el spoofing no funciona en Mininet: cambiar los escenarios amp a usar **hosts reales distintos** (patrón bots) en vez de raw-socket spoof. Editar `iot/attacks/scenarios/{dns,coap,ssdp}_amplification.py`.
- (b) Revisar `iot/devices/servers/{dns,coap,ssdp}_server.py`: que respondan a la query enviada.
- (c) `iot/pipeline/label_dataset.py`: asegurar que el flujo reflector→víctima quede etiquetado AMPLIFICATION; `flow_extractor.py`: capturar bytes bidireccionales.
**Fix de features (durable, hacer siempre):** agregar en `iot/pipeline/feature_engineering.py` ventanas keyed por **destino**: `dst_flows_5s`, `dst_distinct_src_5s`, `dst_pkts_5s`. El reflector bajo carga muestra muchos src distintos → un dst; discrimina amplificación aunque el source sea diverso/spoofeado.
**Re-correr:** `MODE=full bash scripts/rerun_pipeline.sh` (VM).
**Aceptación:** filas amplificación con `tot_bwd_bytes>0` y/o `dst_distinct_src_5s` alto; recall de DNS/CoAP/SSDP > 0.5.
**Riesgo:** depuración de red puede no cerrar en un intento; si spoofing es irreproducible, documentar la limitación y usar el enfoque de bots.

## FASE 3 — Base rate realista en el test (0.5 día) · [ ]
**Problema:** BENIGN capado a 50k (real 1.1M) → test balanceado artificial → precision optimista.
**Fix:** doble reporte en `ml_extra/report.py` / `train_all.py`:
- **Balanceado** (capacidad por clase, el actual).
- **Realista** (proporción natural de despliegue) — no capar BENIGN en test, o re-pesar. Añadir **PR-AUC** por clase.
**Aceptación:** `metrics.json` con ambos regímenes y PR-AUC.

## FASE 4 — Robustez XGB · [x] HECHO (ver Resultados)
**Problema:** XGB cae F1 0.81→0.37 con σ=0.01 (RF aguanta 0.72). Sospechoso.
**Revisar `ml_extra/adversarial.py`:** el ruido se suma en espacio escalado sobre TODAS las features, incluidas binarias (`is_dns`, `is_coap`, `is_ssdp`...). Tras StandardScaler, ruido pequeño flipea flags raros de los que XGB depende.
**Fix:** aplicar ruido solo a features continuas (excluir `is_*`), o en espacio original. Re-evaluar. Corregir path hardcodeado `DS=/home/ubuntu/iot_run/dataset_p1p2_clean13.csv` → usar `--dataset` del run.
**Aceptación:** curva de degradación re-generada; interpretar como fragilidad real vs artefacto.

## FASE 5 — Consolidación y tesis (1 día) · [ ]
- Unificar manejo de imbalance (hoy MLP hace oversample, RF/XGB no).
- (Opcional) pipeline 2-etapas: anomalía (IsoForest/AE) → clasificador multiclase. Resuelve amplificación mejor que multiclase forzado.
- CV con intervalos de confianza en la corrida corregida (actualizar `cv_*.json`, son de mayo).
- Regenerar PDF: `make -f Makefile.iot iot-report RUN=<run>`.
- **Tabla antes/después** en `docs/tesis/Trabajo de Grado - IoT-SDN-AI.docx` + sección "identificación y corrección de data leakage".

---

## Orden recomendado y esfuerzo
1. Fase 0 (0.5h) → 2. Fase 1 (1d, ganancia segura) → 3. Fase 2 (1-2d, VM) → 4. Fase 3 (0.5d) → 5. Fase 4 (0.5d) → 6. Fase 5 (1d).
**Total: ~4-6 días.** Fases 1,3,4 son solo código (editables en host, entrenables en VM en minutos). Fase 2 es la pesada (re-correr red).

## RESULTADOS REALES (ejecutado 2026-09-22, en host con dataset run_20260921)

Todo el código de Fases 0/1/4 y las features `dst_*` de Fase 2 se ejecutaron y
validaron en este host (deps ML instaladas). Solo el re-run de red (Mininet)
queda para la VM.

### Corrección del relato (importante)
La hipótesis inicial "la fuga infla los floods a F1 1.00" resultó **parcial**:
- Los floods bien representados (SYN/ICMP/MIRAI/PORT_SCAN) **mantienen F1 alto
  SIN fuga** → son genuinamente separables. Esa detección es sólida y defendible.
- El verdadero problema es **déficit de diversidad de flujos**: 9 de 14 clases
  tienen tan pocas firmas `(src,dst,dport,proto)` que no son evaluables sin fuga.
  El 0.97/0.82 del baseline descansaba en casi-duplicados filtrados a train+test.

### Métricas honestas — CV agrupada 5-fold (anti-fuga), `cv_grouped.json`
| Modelo | Accuracy | Macro-F1 |
|---|---|---|
| RF  | 0.849 ± 0.139 | 0.683 ± 0.151 |
| XGB | 0.849 ± 0.140 | 0.699 ± 0.121 |

Alta varianza entre folds (RF acc 0.59–0.95) = síntoma del déficit de diversidad
(pocos grupos gigantes por clase). **No es número final: es evidencia de que el
dataset actual no soporta evaluación supervisada rigurosa.**

### Testabilidad por clase (folds con soporte de test, F1 medio) — RF
| Clase | folds testeables | F1 medio | Estado |
|---|---|---|---|
| ICMP_FLOOD | 5/5 | 1.000 | sólida |
| MIRAI_COORDINATED | 5/5 | 0.979 | sólida |
| BENIGN | 5/5 | 0.956 | sólida |
| SYN_FLOOD | 5/5 | 0.930 | sólida |
| PORT_SCAN | 5/5 | 0.823 | sólida |
| CREDENTIAL_BRUTEFORCE | 4/5 | 0.671 | aceptable |
| DNS_AMPLIFICATION | 3/5 | 0.333 | ruido (13 muestras test) |
| COAP_AMPLIFICATION | 3/5 | 0.000 | **rota** (captura) |
| UDP/HTTP/MQTT×2/SLOWLORIS/SSDP | 1/5 | 0.000 | **no evaluable** (1 firma) |

### Fase 4 — adversarial (corregido: ruido solo en features continuas)
Hipótesis "el colapso de XGB era por ruido en flags binarias" → **REFUTADA**.
Aun excluyendo `is_*`, XGB cae F1 0.76→0.27 con σ=0.01 (RF 0.59→0.58). La
fragilidad de XGB es **real** (fronteras de decisión afiladas), no un artefacto.
Hallazgo confirmado y más fuerte. `adversarial_metrics.json` regenerado.

---

## CONCLUSIÓN Y CAMINO CRÍTICO
El bloqueador ya no es "tunear modelos" — es **regenerar datos con diversidad**.
Fase 2 se amplía: no solo capturar la respuesta de amplificación, sino generar,
por clase, **muchos flujos independientes** (varias corridas × varios objetivos ×
parámetros aleatorizados) para que cada clase tenga ≥5 grupos y la CV sea estable.

### Próximos pasos en la VM (`/home/ubuntu/iot-sdn-ai`)
1. Diagnóstico amplificación (por qué `src_uni=1-2`, `tot_bwd_bytes=0`):
   `make -f Makefile.iot iot-attack SCN=dns_amplification DUR=30`
   + `tcpdump` en atacante / reflector / víctima (ver Fase 2 arriba).
2. Regenerar con diversidad: correr `scripts/rerun_pipeline.sh` **N veces** con
   objetivos/params variados (editar escenarios para rotar víctimas reales), o un
   solo run con más objetivos por ataque. Meta: ≥5 firmas por clase.
3. El pipeline ya produce las nuevas features `dst_*` (código actualizado).
4. Re-evaluar: `python ml_extra/eval_grouped_cv.py --dataset data/processed/<run>/dataset.csv`
5. Objetivo de aceptación: 14/14 clases testeables ≥3/5 folds; macro-F1 estable (std < 0.05).

## Estado de fases
- [x] Fase 0 — baseline congelado (`*_baseline_*` en artifacts)
- [x] Fase 1 — split anti-fuga (`common.split_grouped`, `train_all --split grouped`) + CV (`eval_grouped_cv.py`)
- [~] Fase 2 — features `dst_*` en `feature_engineering.py` LISTAS; falta re-run VM + diagnóstico captura
- [x] Suite leak-free (Tier 1): calibration/confusion/explain/report/cross_eval migrados a `split_grouped`
- [x] Arquitectura 2-etapas (Tier 2): `two_stage.py` — detección F1 0.982
- [x] Fase 3 — base-rate realista + PR-AUC (`base_rate.py`, ver RESULTADOS-FINAL.md; XGB detector robusto a prevalencia baja, RF no)
- [x] Fase 4 — adversarial corregido (hipótesis refutada, fragilidad XGB confirmada)
- [ ] Fase 5 — consolidación + tabla en tesis (tras re-run VM)


---

## PERFECCIONAMIENTO Tier 1-2 (ejecutado 2026-09-22)

### Tier 1 — Suite completa ahora leak-free
Todos migrados de `split_scaled` (leaky) → `common.load_and_split` (grouped, fold0 = mismo hold-out que vieron los modelos). Helper nuevo en `common.py`.
- `calibration.py` — Brier RF/XGB **0.049** (antes 0.016 leaky; honesto = peor, esperado). Paths VM hardcodeados eliminados.
- `confusion_analysis.py` — top confusión: **COAP_AMPLIFICATION→BENIGN 100%** (data rota); única confusión supervisada real SYN↔MIRAI 2.5% (ambos TCP flood). UMAP regenerado.
- `report.py` — PDF `report_grouped.pdf` regenerado leak-free + robusto a clases sin soporte.
- `explain.py` — SHAP top features: host_flows_5s, syn_count, host_pkts_5s, host_bytes_5s, host_syn_5s, proto. Dominan agregados host-window (floods). `shap_summary.png`.
- `cross_eval.py` — migrado (listo para CIC).

### Tier 2 — Arquitectura 2-etapas (`two_stage.py`, `two_stage.json`)
5-fold grouped CV. **Separa detección de atribución:**
| Tarea | Métrica |
|---|---|
| **Etapa-1 DETECCIÓN (ATTACK vs BENIGN)** | **F1 0.982±0.014 · recall 0.967 · precision 0.998 · FPR benigno 0.7%** |
| Pipeline 2-etapas (multiclase) | acc 0.849 · macro-F1 0.536±0.116 |
| Baseline 1-etapa (multiclase) | acc 0.849 · macro-F1 0.536±0.113 |

**Lectura:** el 2-etapas NO mejora la atribución fina (mismo techo de diversidad), pero
da el número **deployable fuerte**: detección F1 0.98 al 0.7% FPR, leak-free. Narrativa de
tesis: reportar DETECCIÓN (0.98) y ATRIBUCIÓN (bounded por diversidad) por separado, no un
0.68 mezclado.

### Restante para perfeccionar (host, sin VM)
- Tuning de hiperparámetros con grouped-CV (puede subir algo la atribución).
- Portabilidad: `feature_engineering.py` cross-platform (hoy usa `sort/tail` externos → solo VM).
- Naive baseline leak-free + bootstrap CIs (la std de CV ya cubre dispersión).

### Restante gated por acción tuya
- Descargar CIC-IoT-2023 (`docs/guias/GUIA-CIC-descarga.md`) → validación cruzada externa (`cross_eval.py` listo).
- Reboot PC → VM → regenerar datos con diversidad (el fix de fondo).

---

## SESIÓN 2026-09-24 — Bugs raíz de red/etiquetado + episodios

### Bugs raíz (arreglados)
1. **Loops L2** (`iot/topology/mn_iot_topo.py`): 2 spines × 8 leafs sin STP + FLOOD → storm / MAC flapping. Fix: RSTP en todos los bridges + `_wait_rstp` (≈11 s, 92 puertos fwd / 7 bloqueados).
2. **Antispoof falsos positivos** (`iot/controller/iot_antispoof.py`): validaba puerto en uplinks → DROP a IoT legítimo y a las queries spoofeadas de amplificación. Fix: solo puertos de borde (skip spines + trunks vía LLDP/EventLinkAdd). *Tradeoff:* no detecta spoof de IPs de otra zona (requeriría filtro por subred/uRPF).
3. **Labeler amplificación** (`iot/pipeline/label_dataset.py`): solo matcheaba victim_ip .10; el ataque rocía el /24 → ~1,1 M flujos amp etiquetados BENIGN en run_20260921. Fix `is_amp_flow` (reflector ip:port + /24 + rango sport).
4. **feature_engineering.py**: header sin `flush()` antes de `sort` → header al final → crash. Fix.

**Impacto:** re-etiquetando run_20260921-135634 → BENIGN 2 100 (era ~1,1 M). **Todas las métricas previas (0.973/0.822, detección 0.982) quedan invalidadas.**

### Diversidad por episodios (Fase 2 ampliada)
- `runner.py --episode N`: intensidad ×U[0.5,1.5] con seed por episodio; manifest registra `episode` y `src_ip` real.
- `rerun_pipeline.sh`: warmup benigno 120 s; 13 escenarios × 5 rondas intercaladas; fuente rotando attacker / parkinga / fitnessba / weatherst / beacona (scan y bruteforce siempre attacker: desde zona 4-7 no pasan por s_iot_0).
- Labeler: IP atacante del manifest; no-spoofed exige fuente **y** objetivo (target_ip:port o subred); spoofed (SYN/ICMP/MIRAI) por objetivo+puerto+proto; columna `episode`.
- `ml_extra/common.make_groups`: grupo = episodio (ataque) / dispositivo (benigno). Legacy → firma.
- Smoke validado: HTTP desde 2 bots = 2 grupos; BENIGN 62 grupos; `episode` fuera de X.

### Limitación observada
Reflector DNS (Python) se satura a 5 000 pps: solo ~0,1 % de queries amp reciben respuesta. Señal igual fuerte vía `dst_distinct_src_5s` (=254).

### Run en curso
`run_20260924-174518` (MODE=full, EPISODES=5). Aceptación: 13/13 clases con ≥5 grupos; CV agrupada estable.
