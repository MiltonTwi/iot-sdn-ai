# Resultados FINALES — run_20260924-214452 (documento de trabajo)

**Generado:** 2026-09-24 · **Corrida definitiva** (EPISODES=6). Supersede a
`run_20260924-192239` (ver `RESULTADOS-run_20260924-192239.md`, EPISODES=5).
**NO** es la tesis; consolida los números para revisarlos antes de reescribir el
`.docx`.

Dataset: `data/processed/run_20260924-214452/dataset.csv` — **505 768 filas, 14
clases, TODAS con 6 grupos** (BENIGN 62). CRED_BRUTEFORCE 72→50 000 flujos.
127,7 M paquetes → 18,1 M flujos.

---

## Titular (CV agrupada 5-fold, anti-fuga)

| Modelo | Accuracy | F1-macro |
|---|---|---|
| **Random Forest** | **0,986 ± 0,018** | **0,986 ± 0,014** |
| XGBoost | 0,982 ± 0,020 | 0,958 ± 0,048 |

RF pasa a **modelo principal**: mayor F1-macro y **más estable** (σ 0,014 vs
0,048 de XGB). Mejora sobre EPISODES=5 (RF era 0,976 ± 0,031) por más diversidad.

### Por clase — RF (F1 medio, folds testeables)

| Clase | F1 | recall | folds |
|---|---|---|---|
| HTTP_FLOOD | 1,000 | 1,000 | 3/5 |
| MQTT_MALFORMED | 1,000 | 1,000 | 4/5 |
| MQTT_SUBSCRIBE_FLOOD | 1,000 | 1,000 | 4/5 |
| CREDENTIAL_BRUTEFORCE | 1,000 | 1,000 | 4/5 |
| PORT_SCAN | 1,000 | 1,000 | 4/5 |
| SSDP_AMPLIFICATION | 1,000 | 1,000 | 4/5 |
| COAP_AMPLIFICATION | 0,999 | 1,000 | 3/5 |
| DNS_AMPLIFICATION | 0,999 | 0,999 | 3/5 |
| ICMP_FLOOD | 0,994 | 0,998 | 4/5 |
| SLOWLORIS | 0,991 | 0,983 | 3/5 |
| UDP_FLOOD | 0,991 | 0,984 | 4/5 |
| SYN_FLOOD | 0,986 | 1,000 | 4/5 |
| BENIGN | 0,941 | 0,924 | 5/5 |
| MIRAI_COORDINATED | 0,878 | 0,942 | 3/5 |

Amplificación resuelta (F1 ~1,0). BENIGN mejoró (F1 0,893→0,941; recall
0,837→0,924). Más débil ahora: MIRAI_COORDINATED (0,878) — se confunde con
SYN_FLOOD (ambos TCP flood).

Single-split fold-0 (referencia): RF 0,986/0,979 · XGB 0,998/0,994 · MLP 0,999/0,998.

---

## Detección binaria (ATTACK vs BENIGN) y FP benigno — RESUELTO

2-etapas, umbral por defecto (argmax): recall 0,999 · precision 0,978 · **F1
0,988 ± 0,014** · FPR benigno 0,140.

**Afinado de umbral (`threshold_fp.py`, RF):** bajando el umbral de decisión sobre
P(ataque) a **thr = 0,102**:

| Métrica | Valor |
|---|---|
| Recall (ataque) | 1,000 |
| Precision | 0,999 |
| **FPR benigno** | **0,040 (3,96 %)** |
| F1 | 0,999 |

El FP benigno baja de ~14 % a **<4 %** manteniendo recall ~100 %. **El problema de
falsos positivos queda resuelto vía punto de operación**, sin re-entrenar.

---

## Otros análisis (regenerados sobre este run)

- **Bootstrap CI (fold-0):** RF F1-macro 0,979 [0,978, 0,980]; XGB 0,994 [0,993, 0,995].
- **Calibración (Brier):** RF 0,0022 · XGB 0,0018 (probabilidades fiables).
- **Robustez adversarial** (ruido gaussiano solo en continuas, RF): 0,979 → 0,879
  (σ0,01) → 0,533 (σ0,1) → 0,210 (σ1,0). Motiva entrenamiento adversarial futuro.
- **Latencia:** inferencia ML 0,67 ms (p95 1,44), mitigación REST 3,54 ms.
- **Naive rule-based:** acc 0,244 / F1 0,066 sobre el dataset corregido → las reglas
  fijas no bastan; el ML aporta valor.
- **Mitigación (evidencia cuantitativa):** víctima 895 587 pkts baseline → **0 tras
  DROP (100 % reducción)**, 10 reglas (una por switch).
- **SHAP:** dominan features de comportamiento (host_flows_5s, syn_count, proto) →
  sin fuga por identidad del atacante.
- Artefactos en `ml_extra/artifacts/`: metrics.json, cv_grouped.json, two_stage.json,
  threshold_fp.json, bootstrap_ci.json, calibration_metrics.json, adversarial_metrics.json,
  naive_metrics.json, mitigation_evidence.json, report_run_20260924-214452.pdf, PNGs.

---

## Estado de pendientes

- [x] Fuga train/test → CV agrupada por episodio/dispositivo.
- [x] Amplificación (captura + etiquetado) → F1 ~1,0.
- [x] Diversidad de flujos → 6 grupos/clase (todas), CV estable (σ 0,014).
- [x] CREDENTIAL_BRUTEFORCE → 50 000 flujos (fix hosts vivos).
- [x] **FP benigno** → 3,96 % vía umbral (era ~16 %).
- [x] Naive / bootstrap / latencia → regenerados.
- [x] Mitigación (pega #5) → evidencia 100 % reducción.
- [x] ARP_SPOOF (pega #4) → documentado como limitación (L2, fuera del clasificador
      de flujos; control-plane no capta gateway inexistente).
- [x] **Cross-eval CIC-IoT-2023** → HECHO (Merged01+02, 1,46 M flujos, cap 200k eval).
      **Detección binaria transfiere: F1-ataque 0,940 · AUC 0,948 · recall 0,887 ·
      precision 0,999** (39 features comunes, sin host_*/dst_*). La atribución
      multiclase NO transfiere (acc 0,016) por incompatibilidad de extractores
      (nuestro tshark vs CICFlowMeter de CIC) → rangos de features distintos;
      limitación documentada, no falla del modelo. `cross_eval_cic.json`.
- [ ] MIRAI_COORDINATED 0,878 (confusión con SYN_FLOOD) — limitación menor, documentar.

---

## Cambio de relato para la tesis (pendiente de tu OK para reescribir)

- Titular: **RF, CV agrupada, F1-macro 0,986 ± 0,014** (no split único, no XGB).
- Amplificación: de "lo difícil (recall 0,00-0,21)" → **resuelta** (~1,0).
- Benigno: reportar FP y su **mitigación por umbral** (14 %→4 %).
- Detección binaria: F1 0,988; con umbral, FPR <4 % a recall ~100 %.
- Añadir sección **detección y corrección de data leakage** (casi-duplicados +
  captura/etiquetado rotos) — suma rigor.
- Latencia 0,67 ms (no 34 ms). Mitigación con evidencia cuantitativa (100 %).
- CIC-IoT: marcar pendiente. ARP: limitación de alcance.

## Validación externa — CIC-IoT-2023 (HECHO)

Cross-dataset sobre CIC-IoT-2023 (Merged01+02, 1,46 M flujos reales; 39 features
comunes, `--shared-features`):

| Tarea | Cross-domain |
|---|---|
| **Detección (ATTACK vs BENIGN)** | **F1 0,940 · AUC 0,948 · recall 0,887 · precision 0,999** |
| Atribución (multiclase) | acc 0,016 — NO transfiere |

**Lectura:** la **capacidad de detección generaliza a un dataset externo real**
(F1 0,94, AUC 0,95), evidencia fuerte de que no es sobreajuste al lab. La
atribución fina no transfiere porque CIC usa otro extractor de flujos
(CICFlowMeter) con features de semántica/rango distintos a los nuestros — problema
conocido de cross-dataset NIDS, no un fallo del modelo. Reportar ambas por
separado. `ml_extra/artifacts/cross_eval_cic.json`.

---

**Todo resuelto y consolidado.** Sin bloqueos externos pendientes.

## Fase 3 — Base rate realista + PR-AUC (HECHO 2026-09-26)

`ml_extra/base_rate.py` → `ml_extra/artifacts/base_rate.json`. **Correr en la VM**
(sklearn 1.7.2): con sklearn 1.9 del host `StratifiedGroupKFold` da otro fold-0 y
los pickles no casan → números falsos.

Test fold-0 tiene **prevalencia de ataque 96,7 %** (4616 benignos / 133664 ataques)
→ la precision reportada es optimista. Se re-pesan benignos para simular despliegue.

**PR-AUC por clase (one-vs-rest):** macro 0,999 RF y XGB; peor BENIGN (0,993 / 0,995).

**Detección ATTACK vs BENIGN por prevalencia de ataque** (umbral op = 0,102):

| Prevalencia | RF PR-AUC | RF precision | RF recall@P≥0,9 | XGB PR-AUC | XGB precision | XGB recall@P≥0,9 |
|---|---|---|---|---|---|---|
| 96,7 % (test) | 1,000 | 0,999 | 1,000 | 1,000 | 1,000 | 1,000 |
| 50 % | 0,992 | 0,962 | 1,000 | 1,000 | 0,992 | 0,999 |
| 10 % | 0,934 | 0,737 | 1,000 | 0,999 | 0,933 | 0,999 |
| 1 % | 0,563 | 0,203 | **0,000** | 0,998 | 0,557 | 0,996 |
| 0,1 % | 0,113 | 0,025 | **0,000** | 0,996 | 0,111 | 0,996 |

**Lectura:**
- RF (titular multiclase) **no sirve como detector si el ataque es raro**: a 1 % de
  prevalencia genera ~4 falsas alarmas por alerta real y ningún umbral da P≥0,9.
  Su FPR residual (~4 %) viene de benignos con P(ataque) alta — no se arregla con umbral.
- XGB separa benigno con más confianza: PR-AUC ≥0,996 incluso a 0,1 %; re-afinando
  umbral mantiene recall 0,996 con precision ≥0,9.
- **Recomendación de arquitectura:** etapa 1 detección = XGB (umbral afinado a la
  prevalencia esperada); etapa 2 atribución = RF. Coherente con `two_stage.py`.
- **Caveat:** solo 4616 flujos benignos de test (pocos dispositivos) → a 0,1 % cada
  benigno pesa ~29 000×; las cifras a ≤1 % son de alta varianza. Más benigno
  diverso en futuras corridas lo acotaría.

## Lazo cerrado en vivo: detección → mitigación automática (HECHO 2026-09-26)

Antes la mitigación se disparaba **a mano** (REST). Ahora el ciclo completo corre
solo, sobre ataques reales en Mininet:

```
tcpdump (mirror s_iot_0) → flow_extractor --live (estado persistente, snapshot c/5 s)
  → feature_engineering → live_detector.py [XGB detecta → RF atribuye → incidente]
  → POST /iot/mitigate → reglas OpenFlow en los 10 switches
```

Código: `iot/pipeline/live_capture.sh`, `iot/pipeline/flow_extractor.py --live-dir`,
`ml_extra/live_detector.py`, `ml_extra/closed_loop_eval.py` (+ `closed_loop_rescore.py`).
`make -f Makefile.iot iot-live-start|iot-live-stop|iot-closed-loop`.
Resultado: `ml_extra/artifacts/closed_loop.json`.

**Experimento:** 120 s solo benigno + 13 ataques × 30 s, sin intervención.

| Métrica | Valor |
|---|---|
| Ataques detectados y mitigados | **13/13** |
| Tiempo hasta mitigar (TTM) | mediana **4,0 s**, máx 27,9 s (port scan) |
| Falsas alarmas (120 s benigno, ~5 000 flujos) | **0** |
| Reglas correctas / colaterales sobre benignos | **29/29** / **0** |
| Reducción del tráfico de ataque en el objetivo | mediana **95,1 %**, mín 79,8 % |
| Atribución correcta del tipo (1ª regla) | 10/13 |
| Latencia fin de ventana → regla instalada | ~1-1,7 s |

Por escenario (reducción en víctima; en amplificación, en el reflector):
SYN 99,7 · UDP 100 · ICMP 80,9 · HTTP 97,2 · Slowloris 82,2 · DNS amp 90,2 ·
CoAP amp 79,8 · SSDP amp 94,6 · MQTT sub 97,2 · MQTT malformado 99,7 · Mirai 95,1.
Port scan y fuerza bruta: sin víctima única (se mide solo TTM y acierto).

**Política de mitigación (match mínimo que contiene el ataque):**
- Destino con ≥20 orígenes atacantes (origen falsificado/distribuido): LIMIT 64 kbps
  a dst+proto; amplificación: LIMIT a las consultas hacia el reflector (dst+udp+puerto).
- Origen único: DROP (floods, botnet, fuerza bruta, abuso MQTT, slowloris; TCP con
  handshake → origen auténtico). Recon: LIMIT 512 kbps.
- Servidores de infraestructura nunca se bloquean globalmente (solo pares).

**Bugs/defectos encontrados y corregidos en el camino:**
1. **LIMIT = DROP** (grave): el L2 switch usaba solo tabla 0; la regla LIMIT hacía
   `meter + goto_table:1` a una tabla vacía → 100 % pérdida. Fix: tabla 0 = seguridad
   (miss → goto 1), L2 en tabla 1. Test: `scripts/test_limit.sh`.
2. Mitigación solo por `src_ip`: en amplificación el origen es un servidor legítimo
   (reflector) → bloquearlo tumbaba el DNS de toda la red. Fix: match genérico
   (src/dst/proto/puertos) en `iot_mitigation.py`.
3. Ventanas de 5 s truncaban conexiones largas (slowloris, MQTT) → invisibles al
   modelo. Fix: extractor persistente entre ventanas (snapshots acumulados).
4. Bajo flood (~190 k pps) el procesado por lotes se atrasaba sin fin. Fix: siempre
   la ventana más reciente + muestreo a 20 k filas.
5. Umbral único estricto (P≥0,99989) ocultaba slowloris (P mediana 0,97). Fix: dos
   umbrales (estricto por flujo para destinos distribuidos; 0,9 por origen agregado
   ≥5 flujos y ≥50 % en 3 ventanas). Benignos en vivo: P(ataque) < 0,5.
6. LIMIT 512 kbps no frenaba paquetes pequeños (ICMP 98 B, consultas DNS) → 64 kbps.

**Limitaciones honestas:**
- La atribución en vivo es peor que offline (10/13): slowloris→MQTT_SUB, scan→Mirai,
  MQTT_SUB→MQTT_MALF. La acción elegida sigue siendo correcta (depende de la familia
  y del patrón origen/destino, no de la etiqueta fina).
- LIMIT por destino (ICMP/amplificación) también frena el tráfico legítimo de ese
  tipo hacia ese destino mientras dure la regla (60 s).
- Amplificación en el lab: la "víctima" no recibe respuestas, recibe ~150 ARP/s
  del reflector resolviendo IPs falsificadas inexistentes → se mide en el reflector.
- 1 corrida por escenario (30 s); TTM con varianza entre corridas (SYN 5-10 s).

## MLP bajo CV agrupada (HECHO 2026-09-26)

`eval_grouped_cv.py --models mlp` → `artifacts/cv_grouped_mlp.json`. Mismo protocolo que RF/XGB:

| Modelo | Exactitud | F1-macro |
|---|---|---|
| **RF** | 0,986 ± 0,018 | **0,986 ± 0,014** |
| MLP | 0,987 ± 0,021 | 0,968 ± 0,039 |
| XGB | 0,982 ± 0,020 | 0,958 ± 0,048 |

El 0,998 del MLP en la tesis era de una sola partición favorable (fold 0). En CV cae
en slowloris (F1 0,67) e ICMP (0,89). **RF sigue siendo el mejor multiclase y el más
estable** → la afirmación "ensambles > MLP" pasa a ser cierta si la Tabla 4 usa CV para los tres.

## Lazo cerrado — 5 corridas (HECHO 2026-09-28)

`scripts/closed_loop_reps.sh 5` → `artifacts/closed_loop_r1..r5.json` (r1 = corrida del 09-26);
agregación `ml_extra/closed_loop_aggregate.py` → `artifacts/closed_loop_reps.json`.

| Métrica | Valor |
|---|---|
| Ataques detectados y mitigados | **65/65** |
| Falsas alarmas (5 × 120 s benigno) | **0** |
| Reglas correctas / colaterales | **142/142** / 0 |
| TTM mediana global / máx | **5,3 s** / 34,2 s |
| Mediana de TTM por corrida | 5,1 ± 0,9 s (4,0–6,2) |
| Reducción del tráfico de ataque | mediana **94,6 %**, mín 76,6 % (50 mediciones válidas) |
| Atribución correcta | 48/65 (74 %) |

Por escenario (TTM media ± desv; atribución): SYN 9,3±0,7 (5/5) · UDP 3,8±1,3 (5/5) ·
ICMP 3,2±1,5 (5/5) · HTTP 2,9±1,8 (5/5) · Slowloris 21,8±7,1 (0/5) · Scan 20,9±7,7 (1/5) ·
DNS 3,4±2,0 · CoAP 4,3±1,7 · SSDP 4,0±1,6 (5/5) · MQTT sub 4,9±2,2 (0/5) ·
MQTT malf 17,4±11,3 (2/5) · Bruteforce 11,8±3,0 (5/5) · Mirai 3,2±1,9 (5/5).

**Criterio de reducción medible:** el pico previo debe ser ≥ 2× la línea base. En 3 corridas
MQTT_MALFORMED apenas superó la base del broker (pico ≈ 33 pps vs ≈ 25) → reducción no medible
(detectado y mitigado igual). Los errores de atribución son sistemáticos (slowloris, scan,
MQTT sub), la acción aplicada fue correcta en todos.

## Lazo cerrado optimizado y comparación limpia (HECHO 2026-10-01) — SUPERSEDE las 5 corridas

**Defecto de medición encontrado:** con pausas de 20 s entre escenarios, las retransmisiones
del ataque previo (mismo atacante) disparaban la mitigación antes del nuevo ataque → TTM
artificiales (hasta 0,07 s) y etiqueta de la clase previa. Afectaba también a las 5 corridas
anteriores (p. ej. MQTT_MALFORMED "no medible" era arrastre de MQTT_SUB), que se retiraron.
Todas las cifras vigentes usan `COOLDOWN=60` (> vigencia de las reglas).

**Optimizaciones (commit fe9a439):** ventana en vivo de 2 s con snapshot de 5 s de flujos
(features idénticas a entrenamiento), muestreo a 20 k tras las features y antes de sshfs,
RF atribuye ≤ 2 k flujos, evidencia por origen = flujos distintos en 15 s de captura.

| Métrica (3 corridas c/u, pausa 60 s) | Ventana 5 s | Ventana 2 s |
|---|---|---|
| Detectados y mitigados | 39/39 | 39/39 |
| Falsas alarmas | 0 (360 s) | 0 (960 s, incl. 600 s benignos continuos) |
| Reglas correctas / colaterales | 155/155 / 0 | 243/243 / 0 |
| TTM mediana / máx | 4,7 s / 8,5 s | **2,5 s** / 7,5 s |
| Mediana por corrida | 4,8 ± 0,4 s | 2,6 ± 0,4 s |
| Reducción mediana / mín | 94,6 % / 78,2 % | 95,2 % / 78,1 % |
| Atribución | 33/39 | 33/39 |

Por escenario, TTM 5 s → 2 s: SYN 7,3→5,5 · UDP 3,4→3,0 · ICMP 1,8→2,3 · HTTP 3,9→2,0 ·
Slowloris 7,9→6,3 · Scan 4,9→2,7 · DNS 5,3→1,8 · CoAP 4,2→1,7 · SSDP 2,9→2,3 ·
MQTT sub 4,8→3,2 · MQTT malf 3,9→2,1 · Bruteforce 7,0→4,4 · Mirai 3,4→2,1.
Límite restante: el SYN flood (~200 k pps) satura el extractor en Python.
Artefactos: `closed_loop_cd60_c{5,2}_r{1..3}.json`, `closed_loop_cd60_c{5,2}_reps.json`,
`closed_loop_c2_benign600.json`.
